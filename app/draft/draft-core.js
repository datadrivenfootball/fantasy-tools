// DDF draft tool core, Phase 1 (JEG-1667). Pure functions between the data
// bundle (draft-data.js), the price engine (draft-engine.js, not edited
// here) and the page (draft-app.js). No DOM, no network. Runs in the
// browser (window.DraftCore) and under Node.
//
// What it does:
//   1. buildModel: bundle + league + overrides -> ours, market and platform
//      prices through the engine, exactly as tools/draft_backtest.mjs shapes
//      them, plus tiers by position.
//   2. derive / board: draft state (league, picks) -> each team's money and
//      open slots -> the engine's board (walk-away, buy limit, push floor B,
//      max bids, inflation).
//   3. tierCliffs, rosterSummary: what is left in each tier; my open
//      starters, bye collisions, starter value against roster value.
//   4. Link codec: any state <-> "#s=<token>+<check>" (LINK-FORMAT.md
//      wrapper and check; format version 2 = a draft-tool state).
//
// state = {v: 1, league, me: team index, picks: [[playerKey, teamIndex,
//   price]], overrides: {playerKey: DDF Value}, ourFactor: "personal"|"room"}
// league = {platform, leagueId, name, teams: [{name, budget}], budget, minBid,
//   slots: {QB,RB,WR,TE,FLEX,SUPERFLEX,K,DST,BN}, scoring: {per-stat points},
//   scoringLabel, notes}
(function (root) {
  "use strict";

  var E = root.DraftEngine;
  if (!E && typeof require === "function") E = require("./draft-engine.js");

  var SKILL = ["QB", "RB", "WR", "TE"];
  var SLOT_KEYS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST", "BN"];
  var STARTER_SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST"];
  var SCORING_KEYS = ["pass_yds", "pass_tds", "ints", "rush_yds", "rush_tds", "rec", "rec_yds", "rec_tds", "fum_lost"];
  // A tier is a price band: it holds every player at the position priced
  // within the larger of $3 and 20% of the tier's best player.
  var TIER_GAP_DOLLARS = 3, TIER_GAP_SHARE = 0.2;

  // ----------------------------------------------------------------- league
  function defaultLeague() {
    var teams = [];
    for (var i = 1; i <= 12; i += 1) teams.push({ name: "Team " + i, budget: 200 });
    return { platform: "manual", leagueId: null, name: "My league", teams: teams, budget: 200, minBid: 1,
      slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, K: 1, DST: 1, BN: 6 },
      scoring: Object.assign({}, E.SCORING_PRESETS.half), scoringLabel: "Half PPR", notes: [] };
  }

  function int(x, lo, hi, dflt) {
    var v = Math.floor(Number(x));
    return isFinite(v) && v >= lo && v <= hi ? v : dflt;
  }

  // One canonical shape, so a state survives a link round trip unchanged.
  function normalizeLeague(l) {
    var d = defaultLeague();
    l = l || {};
    var budget = int(l.budget, 1, 100000, d.budget);
    var teams = (Array.isArray(l.teams) && l.teams.length >= 2 && l.teams.length <= 32 ? l.teams : d.teams).map(function (t, i) {
      return { name: String((t && t.name) || "Team " + (i + 1)).slice(0, 40), budget: int(t && t.budget, 0, 100000, budget) };
    });
    var slots = {};
    SLOT_KEYS.forEach(function (k) { slots[k] = int(l.slots && l.slots[k], 0, 30, l.slots ? 0 : d.slots[k]); });
    var scoring = {};
    SCORING_KEYS.forEach(function (k) {
      var v = Number(l.scoring && l.scoring[k]);
      scoring[k] = l.scoring && isFinite(v) ? v : d.scoring[k];
    });
    return { platform: String(l.platform || d.platform), leagueId: l.leagueId == null ? null : String(l.leagueId),
      name: String(l.name || d.name).slice(0, 60), teams: teams, budget: budget, minBid: int(l.minBid, 1, 100, 1),
      slots: slots, scoring: scoring, scoringLabel: String(l.scoringLabel || scoringLabel(scoring)),
      notes: (Array.isArray(l.notes) ? l.notes : []).map(String).slice(0, 20) };
  }

  function scoringLabel(scoring) {
    var rec = Number(scoring && scoring.rec) || 0;
    return rec >= 0.75 ? "PPR" : rec >= 0.25 ? "Half PPR" : "Standard";
  }

  // The league the engine prices: its budget is the room's mean budget, so
  // prices add up to the money actually in the room when budgets differ.
  function engineLeague(league) {
    var total = league.teams.reduce(function (t, x) { return t + x.budget; }, 0);
    return { teams: league.teams.length, budget: total / league.teams.length, minBid: league.minBid,
      scoring: league.scoring, slots: league.slots };
  }

  // Published formats closest to the league's scoring (as the backtest does:
  // ESPN publishes Standard and PPR only).
  function ecrFormat(league) {
    var rec = Number(league.scoring.rec) || 0;
    return rec >= 0.75 ? "PPR" : rec >= 0.25 ? "HALF" : "STD";
  }
  function espnFormat(league) { return (Number(league.scoring.rec) || 0) >= 0.25 ? "PPR" : "STD"; }

  // ------------------------------------------------------------------ model
  // -> {league (engine shape), players: {key: bundle row}, pos, prices: {ours,
  //    market, platform, source}, values (DDF Value), tiers: {key: n}, order:
  //    [keys by our price], counts, vegasUsed, formats}
  function buildModel(bundle, league, overrides, lineupConfig) {
    var el = engineLeague(league);
    var players = {}, pos = {}, enginePlayers = {}, proj = {}, vegas = {}, ecr = {}, platformRaw = {}, curve = [];
    var fmt = ecrFormat(league), efmt = espnFormat(league);
    bundle.players.forEach(function (p) {
      players[p.key] = p; pos[p.key] = p.pos;
      if (SKILL.indexOf(p.pos) === -1) return;
      enginePlayers[p.key] = { pos: p.pos, name: p.name };
      if (p.proj) proj[p.key] = p.proj;
      if (p.vegas) { var s = E.vegasStatLine(p.vegas, p.proj); if (s) vegas[p.key] = s; }
      if (p.ecr[fmt] && p.ecr[fmt].rank != null) ecr[p.key] = p.ecr[fmt].rank;
      var d = p.espn[efmt];
      if (d != null) { platformRaw[p.key] = d; if (d > 0) curve.push(d); }
    });
    var marketRaw = E.rankImpliedDollars(ecr, curve);
    var build = E.ddfDraftValues({ league: el, players: enginePlayers, projections: { fp: proj }, vegas: vegas,
      markets: { fp_ecr: marketRaw }, lineupConfig: lineupConfig, overrides: overrides || {} });
    var prices = E.boardPrices(build, el, E.rescaleDollars(marketRaw, el), E.rescaleDollars(platformRaw, el));
    var order = Object.keys(players).sort(function (a, b) {
      var d = (prices.ours[b] || 0) - (prices.ours[a] || 0);
      if (d) return d;
      var m = (prices.market[b] || 0) - (prices.market[a] || 0);
      return m || (a < b ? -1 : a > b ? 1 : 0);
    });
    return { league: el, players: players, pos: pos, prices: prices, values: build.values, tiers: tiersOf(prices.ours, pos),
      order: order, counts: build.counts, vegasUsed: build.vegasUsed, formats: { ecr: fmt, espn: efmt } };
  }

  // Tier per priced player, by position, from our prices.
  function tiersOf(ours, pos) {
    var out = {};
    SKILL.forEach(function (ps) {
      var keys = Object.keys(ours).filter(function (k) { return pos[k] === ps; })
        .sort(function (a, b) { return ours[b] - ours[a] || (a < b ? -1 : 1); });
      var tier = 1, best = keys.length ? ours[keys[0]] : 0;
      keys.forEach(function (k) {
        if (best - ours[k] >= Math.max(TIER_GAP_DOLLARS, TIER_GAP_SHARE * best)) { tier += 1; best = ours[k]; }
        out[k] = tier;
      });
    });
    return out;
  }

  // ------------------------------------------------------------------ state
  function newState(league) {
    return { v: 1, league: normalizeLeague(league), me: 0, picks: [], overrides: {}, ourFactor: "personal" };
  }

  function normalizeState(s) {
    var league = normalizeLeague(s && s.league);
    var seen = {}, picks = [];
    ((s && s.picks) || []).forEach(function (p) {
      if (!Array.isArray(p) || p.length < 3) return;
      var key = String(p[0]), team = int(p[1], 0, league.teams.length - 1, -1), price = int(p[2], 0, 100000, -1);
      if (team < 0 || price < 0 || seen[key]) return;
      seen[key] = 1; picks.push([key, team, price]);
    });
    var overrides = {};
    Object.keys((s && s.overrides) || {}).sort().forEach(function (k) {
      var v = Number(s.overrides[k]);
      if (isFinite(v) && v >= 0 && v <= 200) overrides[k] = Math.round(v * 10) / 10;
    });
    return { v: 1, league: league, me: int(s && s.me, 0, league.teams.length - 1, 0), picks: picks,
      overrides: overrides, ourFactor: s && s.ourFactor === "room" ? "room" : "personal" };
  }

  // Fill a team's slots with the players it owns: each position's own slots
  // take its best players, then FLEX (RB/WR/TE), then SUPERFLEX, then the
  // bench. rank(key) orders "best" (our pre-draft price, else the price paid).
  // -> {assigned: [{key, slot, price}], open: {slot: n}, overflow: n}
  function assignSlots(slots, owned, pos, rank) {
    var open = {};
    SLOT_KEYS.forEach(function (k) { open[k] = Math.max(0, Math.floor(Number(slots[k]) || 0)); });
    var sorted = owned.slice().sort(function (a, b) { return rank(b) - rank(a) || (a.key < b.key ? -1 : 1); });
    var slotOf = {};
    function place(filter, slot) {
      sorted.forEach(function (o) {
        if (slotOf[o.key] || open[slot] <= 0 || !filter(pos[o.key])) return;
        slotOf[o.key] = slot; open[slot] -= 1;
      });
    }
    SKILL.concat(["K", "DST"]).forEach(function (ps) { place(function (p) { return p === ps; }, ps); });
    place(function (p) { return p === "RB" || p === "WR" || p === "TE"; }, "FLEX");
    place(function (p) { return SKILL.indexOf(p) !== -1; }, "SUPERFLEX");
    place(function () { return true; }, "BN");
    var overflow = 0;
    var assigned = owned.map(function (o) {
      if (!slotOf[o.key]) overflow += 1;
      return { key: o.key, slot: slotOf[o.key] || "OVER", price: o.price };
    });
    return { assigned: assigned, open: open, overflow: overflow };
  }

  // -> {teams: [{id, name, budget, spent, budgetLeft, open, roster, overflow}],
  //    available: [keys in board order], sold: {key: [teamIndex, price]}}
  function derive(state, model) {
    var sold = {}, owned = state.league.teams.map(function () { return []; });
    state.picks.forEach(function (p) {
      sold[p[0]] = [p[1], p[2]];
      owned[p[1]].push({ key: p[0], price: p[2] });
    });
    var rank = function (o) { var v = model.prices.ours[o.key]; return isFinite(v) ? v : 0; };
    var teams = state.league.teams.map(function (t, i) {
      var a = assignSlots(state.league.slots, owned[i], model.pos, rank);
      var spent = owned[i].reduce(function (s, o) { return s + o.price; }, 0);
      return { id: i, name: t.name, budget: t.budget, spent: spent, budgetLeft: t.budget - spent,
        open: a.open, roster: a.assigned, overflow: a.overflow };
    });
    return { teams: teams, sold: sold, available: model.order.filter(function (k) { return !sold[k]; }) };
  }

  function engineState(state, model, derived) {
    return { league: model.league, me: state.me, ourFactor: state.ourFactor,
      teams: derived.teams.map(function (t) { return { id: t.id, budgetLeft: t.budgetLeft, open: t.open }; }),
      available: derived.available, pos: model.pos, prices: model.prices };
  }

  // The whole board for a state: one call per sale. -> {derived, board,
  // rows: {key: engine row}, inflation: {personal, room, market, platform}}
  function board(state, model) {
    var derived = derive(state, model);
    var b = E.board(engineState(state, model, derived));
    var rows = {};
    b.rows.forEach(function (r) { rows[r.key] = r; });
    var inf = b.inflation;
    return { derived: derived, board: b, rows: rows,
      inflation: { personal: inf.ours.personalFactor, room: inf.ours.factor,
        market: inf.market ? inf.market.factor : null, platform: inf.platform ? inf.platform.factor : null,
        moneyLeft: inf.ours.moneyLeft, valueLeft: inf.ours.valueLeft, openSlots: inf.ours.openSlots } };
  }

  // ------------------------------------------------------------ tier cliffs
  // Per position: the best tier still on the board, how many of it are left,
  // and the dollar drop to the best player of the next tier (pre-draft ours).
  function tierCliffs(model, available) {
    var out = [];
    SKILL.forEach(function (ps) {
      var keys = available.filter(function (k) { return model.pos[k] === ps && model.tiers[k] != null; });
      if (!keys.length) { out.push({ pos: ps, tier: null, left: 0, names: [], next: null, drop: null }); return; }
      var top = keys.reduce(function (m, k) { return Math.min(m, model.tiers[k]); }, Infinity);
      var inTier = keys.filter(function (k) { return model.tiers[k] === top; });
      var rest = keys.filter(function (k) { return model.tiers[k] > top; });
      var low = inTier.reduce(function (m, k) { return Math.min(m, model.prices.ours[k]); }, Infinity);
      var next = rest.length ? rest.reduce(function (m, k) { return Math.max(m, model.prices.ours[k]); }, 0) : null;
      out.push({ pos: ps, tier: top, left: inTier.length, keys: inTier,
        nextTier: rest.length ? rest.reduce(function (m, k) { return Math.min(m, model.tiers[k]); }, Infinity) : null,
        next: next, drop: next == null ? null : low - next });
    });
    return out;
  }

  // ---------------------------------------------------------------- roster
  // My roster: every slot (filled or open), open starters, bye weeks shared
  // by two or more starters, and DDF Value and dollars in starters against
  // the whole roster.
  function rosterSummary(state, model, derived) {
    var me = derived.teams[state.me];
    var bySlot = {};
    me.roster.forEach(function (r) { (bySlot[r.slot] = bySlot[r.slot] || []).push(r); });
    var slots = [];
    SLOT_KEYS.concat(["OVER"]).forEach(function (slot) {
      var filled = (bySlot[slot] || []).slice().sort(function (a, b) { return b.price - a.price; });
      filled.forEach(function (r) {
        var p = model.players[r.key] || {};
        slots.push({ slot: slot, key: r.key, name: p.name || r.key, pos: model.pos[r.key], bye: p.bye, price: r.price,
          value: model.values[r.key] == null ? null : model.values[r.key] });
      });
      for (var i = 0; i < (me.open[slot] || 0); i += 1) slots.push({ slot: slot, key: null });
    });
    var starters = slots.filter(function (s) { return s.key && s.slot !== "BN" && s.slot !== "OVER"; });
    var all = slots.filter(function (s) { return s.key; });
    var sum = function (list, f) { return list.reduce(function (t, s) { return t + (s[f] || 0); }, 0); };
    var byWeek = {};
    starters.forEach(function (s) { if (s.bye != null) (byWeek[s.bye] = byWeek[s.bye] || []).push(s.name); });
    var collisions = Object.keys(byWeek).map(Number).sort(function (a, b) { return a - b; })
      .filter(function (w) { return byWeek[w].length >= 2; })
      .map(function (w) { return { week: w, players: byWeek[w] }; });
    var openStarters = STARTER_SLOTS.filter(function (k) { return me.open[k] > 0; })
      .map(function (k) { return { slot: k, count: me.open[k] }; });
    var rosterValue = sum(all, "value"), starterValue = sum(starters, "value");
    return { slots: slots, openStarters: openStarters, byeCollisions: collisions,
      starterValue: starterValue, rosterValue: rosterValue,
      starterShare: rosterValue > 0 ? starterValue / rosterValue : null,
      starterDollars: sum(starters, "price"), rosterDollars: sum(all, "price"),
      spent: me.spent, budgetLeft: me.budgetLeft, overflow: me.overflow };
  }

  // ------------------------------------------------------------ link codec
  // "#s=<token>+<check>" as in LINK-FORMAT.md: token = base64url of the
  // payload, check = 2 base64url characters from CRC-16/CCITT-FALSE over the
  // token. Payload byte 0 = format version 2 in the top 3 bits (the trade
  // site's decoders reject anything but 1, so a draft link fails closed
  // there) and kind 1 (draft state) in the low 5; the rest is deflate-raw of
  // the UTF-8 JSON state.
  var B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  var LINK_HEADER = (2 << 5) | 1;

  function toBase64Url(bytes) {
    var out = "";
    for (var i = 0; i < bytes.length; i += 3) {
      var b0 = bytes[i], b1 = bytes[i + 1], b2 = bytes[i + 2];
      out += B64[b0 >> 2] + B64[((b0 & 3) << 4) | ((b1 || 0) >> 4)];
      if (i + 1 < bytes.length) out += B64[((b1 & 15) << 2) | ((b2 || 0) >> 6)];
      if (i + 2 < bytes.length) out += B64[b2 & 63];
    }
    return out;
  }
  function fromBase64Url(text) {
    if (!/^[A-Za-z0-9_-]*$/.test(text) || text.length % 4 === 1) return null;
    var out = new Uint8Array(Math.floor(text.length * 3 / 4));
    var acc = 0, bits = 0, n = 0;
    for (var i = 0; i < text.length; i += 1) {
      acc = (acc << 6) | B64.indexOf(text[i]); bits += 6;
      if (bits >= 8) { bits -= 8; out[n] = (acc >> bits) & 255; n += 1; acc &= (1 << bits) - 1; }
    }
    return out.subarray(0, n);
  }
  function crc16(text) {
    var crc = 0xFFFF;
    for (var i = 0; i < text.length; i += 1) {
      crc ^= text.charCodeAt(i) << 8;
      for (var b = 0; b < 8; b += 1) crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xFFFF : (crc << 1) & 0xFFFF;
    }
    return crc;
  }
  function checkChars(token) {
    var c = crc16(token);
    return B64[(c >> 10) & 63] + B64[(c >> 4) & 63];
  }
  function pipe(bytes, stream) {
    var w = stream.writable.getWriter();
    w.write(bytes); w.close();
    return new root.Response(stream.readable).arrayBuffer().then(function (b) { return new Uint8Array(b); });
  }

  // -> Promise<"token+check">. Rejects Error("unsupported") without
  // CompressionStream (Safari before 16.4).
  function encodeState(state) {
    if (typeof root.CompressionStream !== "function") return Promise.reject(new Error("unsupported"));
    var json = JSON.stringify(normalizeState(state));
    return pipe(new root.TextEncoder().encode(json), new root.CompressionStream("deflate-raw")).then(function (packed) {
      var payload = new Uint8Array(packed.length + 1);
      payload[0] = LINK_HEADER; payload.set(packed, 1);
      var token = toBase64Url(payload);
      return token + "+" + checkChars(token);
    });
  }

  // The "s" value of a fragment ("#s=...&x=1"), or the text itself.
  function fragmentToken(text) {
    var t = String(text || "").trim();
    if (t.indexOf("#") !== -1) t = t.slice(t.lastIndexOf("#") + 1);
    var m = /(?:^|&)s=([^&]*)/.exec(t);
    if (m) return m[1];
    return /^[A-Za-z0-9_-]{8,}(?:\+|%2B|%20| )[A-Za-z0-9_-]{2}\W*$/i.test(t) ? t : null;
  }

  // -> Promise<state | {error: "checksum"|"format"|"unsupported"} | null>
  // (null: no state in the text). The separator may be "+", a space or
  // "%2B"; trailing punctuation after the check is ignored.
  function decodeLink(text) {
    var raw = fragmentToken(text);
    if (!raw) return Promise.resolve(null);
    var m = /^([A-Za-z0-9_-]+)(?:\+|%2B|%20| )([A-Za-z0-9_-]{2})[^A-Za-z0-9_-]*$/i.exec(raw);
    if (!m) return Promise.resolve({ error: "format" });
    if (checkChars(m[1]) !== m[2]) return Promise.resolve({ error: "checksum" });
    var bytes = fromBase64Url(m[1]);
    if (!bytes || bytes.length < 2 || bytes[0] !== LINK_HEADER) return Promise.resolve({ error: "format" });
    if (typeof root.DecompressionStream !== "function") return Promise.resolve({ error: "unsupported" });
    return pipe(bytes.subarray(1), new root.DecompressionStream("deflate-raw")).then(function (plain) {
      var s = JSON.parse(new root.TextDecoder().decode(plain));
      if (!s || s.v !== 1 || !s.league || !Array.isArray(s.picks)) return { error: "format" };
      return normalizeState(s);
    }).catch(function () { return { error: "format" }; });
  }

  var DraftCore = {
    SLOT_KEYS: SLOT_KEYS, STARTER_SLOTS: STARTER_SLOTS, SCORING_KEYS: SCORING_KEYS,
    TIER_GAP_DOLLARS: TIER_GAP_DOLLARS, TIER_GAP_SHARE: TIER_GAP_SHARE,
    defaultLeague: defaultLeague, normalizeLeague: normalizeLeague, scoringLabel: scoringLabel,
    engineLeague: engineLeague, ecrFormat: ecrFormat, espnFormat: espnFormat,
    buildModel: buildModel, tiersOf: tiersOf,
    newState: newState, normalizeState: normalizeState, assignSlots: assignSlots, derive: derive,
    engineState: engineState, board: board, tierCliffs: tierCliffs, rosterSummary: rosterSummary,
    encodeState: encodeState, decodeLink: decodeLink, checkChars: checkChars, crc16: crc16,
    LINK_HEADER: LINK_HEADER
  };
  root.DraftCore = DraftCore;
  if (typeof module !== "undefined" && module.exports) module.exports = DraftCore;
})(typeof globalThis !== "undefined" ? globalThis : this);
