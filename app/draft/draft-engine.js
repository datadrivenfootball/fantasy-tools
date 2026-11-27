// DDF draft tool price engine, Phase 0 (JEG-1667). Pure functions, no DOM,
// no network: runs in the browser (window.DraftEngine) and under Node
// (require). Not loaded by any live page.
//
// What it does (spec: docs/draft-tool/engine.md):
//   1. Scoring: season stat lines -> fantasy points for the league's scoring.
//   2. Vegas: season-long player prop lines -> a stat line (missing stats
//      filled from a projection), so Vegas enters as one more projection.
//   3. Ours (DDF draft value): the existing value build,
//      ValueModel.runValuePipeline, run at the league's setting with the
//      live page's expected-starts parameters (DDF bench share). No math is
//      forked: this file only shapes inputs and reads blended DDF Value.
//   4. Dollars: DDF Value (or any weight) -> auction dollars for the league's
//      teams, budget and roster, and a snake rank.
//   5. Market and platform prices: raw published dollars (or a published
//      rank mapped onto a dollar curve) rescaled to the league.
//   6. Live auction math: inflation, max bid per team, walk-away price and
//      push floor.
(function (root) {
  "use strict";

  var ValueModel = root.ValueModel;
  if (!ValueModel && typeof require === "function") {
    ValueModel = require("../trade-value-chart/assets/value-model.js");
  }

  var VERSION = "draft-engine/0";
  var SKILL_POSITIONS = ["QB", "RB", "WR", "TE"];
  var MIN_BID_POSITIONS = ["K", "DST"];
  var SEASON_GAMES = 17;
  var EPS = 1e-9;

  // ---------------------------------------------------------------- scoring
  // Per-stat points, ESPN defaults (interception -2). Yahoo's defaults differ
  // only on interceptions (-1): the yahoo_* presets.
  var SCORING_BASE = {
    pass_yds: 0.04, pass_tds: 4, ints: -2, rush_yds: 0.1, rush_tds: 6,
    rec: 0, rec_yds: 0.1, rec_tds: 6, fum_lost: -2
  };
  var SCORING_PRESETS = {
    standard: Object.assign({}, SCORING_BASE),
    half: Object.assign({}, SCORING_BASE, { rec: 0.5 }),
    ppr: Object.assign({}, SCORING_BASE, { rec: 1 }),
    yahoo_standard: Object.assign({}, SCORING_BASE, { ints: -1 }),
    yahoo_half: Object.assign({}, SCORING_BASE, { ints: -1, rec: 0.5 }),
    yahoo_ppr: Object.assign({}, SCORING_BASE, { ints: -1, rec: 1 })
  };
  var STAT_KEYS = Object.keys(SCORING_BASE);

  function scoringRules(scoring) {
    if (typeof scoring === "string") {
      if (!SCORING_PRESETS[scoring]) throw new Error("unknown scoring preset " + scoring);
      return SCORING_PRESETS[scoring];
    }
    return Object.assign({}, SCORING_BASE, scoring || {});
  }

  function fantasyPoints(stats, scoring) {
    var rules = scoringRules(scoring);
    var pts = 0;
    STAT_KEYS.forEach(function (k) {
      var v = Number(stats && stats[k]);
      if (isFinite(v)) pts += v * rules[k];
    });
    return pts;
  }

  // ------------------------------------------------------------------ Vegas
  // Season-long prop markets (DraftKings "Player Futures", FanDuel "Regular
  // Season") -> stat keys. A prop line is the book's median, not its mean.
  var VEGAS_MARKETS = {
    season_pass_yds: "pass_yds", season_pass_tds: "pass_tds", season_rush_yds: "rush_yds",
    season_rush_tds: "rush_tds", season_receptions: "rec", season_rec_yds: "rec_yds",
    season_rec_tds: "rec_tds"
  };

  // lines: {market: line}. fallback: a projection's stat line for the same
  // player; stats with no prop take the fallback's value. Returns null when
  // the player has no prop at all (Vegas has no opinion on him).
  function vegasStatLine(lines, fallback) {
    var out = {}, covered = [];
    STAT_KEYS.forEach(function (k) { out[k] = Number(fallback && fallback[k]) || 0; });
    Object.keys(lines || {}).forEach(function (market) {
      var stat = VEGAS_MARKETS[market];
      var v = Number(lines[market]);
      if (stat && isFinite(v)) { out[stat] = v; covered.push(stat); }
    });
    if (!covered.length) return null;
    out.covered = covered;
    return out;
  }

  // ----------------------------------------------------------------- league
  // league = {teams, budget, minBid?, scoring, slots: {QB, RB, WR, TE, FLEX,
  // SUPERFLEX, K, DST, BN}}. IR slots are filled after the draft and ignored.
  function leagueShape(league) {
    var s = league.slots || {};
    var n = function (k) { return Math.max(0, Math.floor(Number(s[k]) || 0)); };
    var rosterSize = SKILL_POSITIONS.concat(MIN_BID_POSITIONS, ["FLEX", "SUPERFLEX", "BN"])
      .reduce(function (t, k) { return t + n(k); }, 0);
    var minBidSlots = n("K") + n("DST");
    return {
      teams: Math.floor(Number(league.teams)),
      budget: Number(league.budget),
      minBid: league.minBid == null ? 1 : Number(league.minBid),
      rosterSize: rosterSize,
      minBidSlotsPerTeam: minBidSlots,
      valuedSlotsPerTeam: rosterSize - minBidSlots,
      slots: { QB: n("QB"), RB: n("RB"), WR: n("WR"), TE: n("TE"), FLEX: n("FLEX"),
        SUPERFLEX: n("SUPERFLEX"), K: n("K"), DST: n("DST"), BN: n("BN") }
    };
  }

  // The value build's setting for this league (VP setting shape).
  function pipelineSetting(league) {
    var sh = leagueShape(league);
    return {
      teams: sh.teams,
      slots: { QB: sh.slots.QB, RB: sh.slots.RB, WR: sh.slots.WR, TE: sh.slots.TE },
      flex: sh.slots.FLEX,
      superflex: sh.slots.SUPERFLEX,
      bench_per_team: sh.slots.BN
    };
  }

  // Preseason expected-starts parameters: the live page's lineup config with
  // the window opened at week 1 (the whole season is ahead at draft time).
  function preseasonLineup(lineupConfig, contentWeek) {
    if (!lineupConfig) return null;
    return ValueModel.resolveLineupParameters(lineupConfig,
      { content_week: contentWeek == null ? 1 : contentWeek });
  }

  // ------------------------------------------------------- ours: DDF values
  // Jeremy, 2026-11-27: "Our values are going to be informed by market +
  // vegas projected performance outcomes, calculated up in to DDF draft
  // values." DDF Value's default basis averages the chart sources only
  // (JEG-1073), so a projection would not move ours. Ours therefore uses the
  // value build's own "blend" basis (VP-6.3, basisConfig) over three groups;
  // each group's weight is split evenly across its sources, and a player's
  // mean is re-normalised over the sources that price him (vpWeightedMean).
  // This is the one named setting for the blend (percent per group).
  var DRAFT_BASIS_WEIGHTS = { market: 50, projections: 25, vegas: 25 };

  function draftBasisConfig(groups, weights) {
    var w = weights || DRAFT_BASIS_WEIGHTS;
    var out = { mode: "blend", sources: [], weights: {} };
    Object.keys(groups).forEach(function (g) {
      var keys = groups[g];
      var gw = Number(w[g]) || 0;
      if (!keys.length || gw <= 0) return;
      keys.forEach(function (k) { out.sources.push(k); out.weights[k] = gw / keys.length; });
    });
    return out.sources.length ? out : null;
  }

  // input = {league, players: {key: {pos, name?}},
  //   projections: {sourceKey: {playerKey: stat line | season points}},
  //   vegas: {playerKey: stat line from vegasStatLine} (optional),
  //   markets: {sourceKey: {playerKey: native value (dollars or chart value)}},
  //   lineupConfig: config/lineup_parameters.json (required: it sets DDF's
  //   bench share), basisWeights: {market, projections, vegas} (optional;
  //   default DRAFT_BASIS_WEIGHTS), overrides: {playerKey: DDF value}}.
  // Projections and Vegas enter the value build as "projection" sources in
  // points per game; markets as "chart" sources. Returns {values: {key: DDF
  // Value}, pipeline, basis}.
  function ddfDraftValues(input) {
    var league = input.league;
    if (!input.lineupConfig) throw new Error("lineupConfig is required (it sets DDF's bench share)");
    var sources = {};
    var groups = { market: [], projections: [], vegas: [] };
    var addProjection = function (src, table, group) {
      var vals = {};
      Object.keys(table).forEach(function (k) {
        var row = table[k];
        var pts = typeof row === "number" ? row : fantasyPoints(row, league.scoring);
        if (isFinite(pts)) vals[k] = pts / SEASON_GAMES;
      });
      sources[src] = { family: "projection", status: "included", values: vals, label: src };
      groups[group].push(src);
    };
    Object.keys(input.projections || {}).forEach(function (src) {
      addProjection(src, input.projections[src], "projections");
    });
    if (input.vegas && Object.keys(input.vegas).length) addProjection("vegas", input.vegas, "vegas");
    Object.keys(input.markets || {}).forEach(function (src) {
      var vals = {};
      var table = input.markets[src];
      Object.keys(table).forEach(function (k) {
        var v = Number(table[k]);
        if (isFinite(v)) vals[k] = v;
      });
      sources[src] = { family: "chart", status: "included", values: vals, label: src };
      groups.market.push(src);
    });
    var players = {};
    Object.keys(input.players).forEach(function (k) {
      var p = input.players[k];
      if (SKILL_POSITIONS.indexOf(p.pos) !== -1) players[k] = { pos: p.pos, name: p.name };
    });
    var basis = draftBasisConfig(groups, input.basisWeights);
    var pipeline = ValueModel.runValuePipeline({
      setting: pipelineSetting(league),
      players: players,
      sources: sources,
      basisConfig: basis,
      lineup: preseasonLineup(input.lineupConfig, input.contentWeek)
    });
    var values = {};
    Object.keys(pipeline.rows || {}).forEach(function (k) {
      var entry = pipeline.rows[k].ddfByVersion && pipeline.rows[k].ddfByVersion.blended;
      var v = entry ? entry.value : null;
      if (typeof v === "number" && isFinite(v)) values[k] = v;
    });
    Object.keys(input.overrides || {}).forEach(function (k) {
      var v = Number(input.overrides[k]);
      if (isFinite(v) && v >= 0) values[k] = v;
    });
    return { values: values, pipeline: pipeline, basis: basis };
  }

  // ---------------------------------------------------------------- dollars
  function sortedKeys(weights) {
    return Object.keys(weights).sort(function (a, b) {
      var d = weights[b] - weights[a];
      return d !== 0 ? d : (a < b ? -1 : a > b ? 1 : 0);
    });
  }

  // weights {key: w >= 0} -> {key: dollars}. The league's top N players by
  // weight (N = teams x valued roster slots) split the surplus dollars
  // (every dollar above the $1-per-slot floor, K and DST included in the
  // floor) in proportion to weight, on top of the minimum bid. Players past
  // N, or with weight 0, get no price. Sum of prices + minBid x (empty pool
  // slots + K/DST slots) = teams x budget.
  function pricesFromWeights(weights, league) {
    var sh = leagueShape(league);
    var poolSize = sh.teams * sh.valuedSlotsPerTeam;
    var surplus = sh.teams * sh.budget - sh.teams * sh.rosterSize * sh.minBid;
    var pool = sortedKeys(weights).filter(function (k) { return weights[k] > 0; }).slice(0, poolSize);
    var total = pool.reduce(function (t, k) { return t + weights[k]; }, 0);
    var out = {};
    pool.forEach(function (k) { out[k] = sh.minBid + (total > 0 ? weights[k] / total * surplus : 0); });
    return out;
  }

  // Ours in dollars: DDF Value is a share of a fixed pie, so it splits the
  // surplus directly.
  function ourPrices(ddfValues, league) { return pricesFromWeights(ddfValues, league); }

  // Market or platform dollars quoted for a reference league (FantasyPros
  // and ESPN quote 12 or 10 teams, $200) rescaled to this league: each
  // player's dollars above the minimum keep their share of the surplus.
  function rescaleDollars(rawDollars, league) {
    var sh = leagueShape(league);
    var w = {};
    Object.keys(rawDollars).forEach(function (k) {
      var v = Number(rawDollars[k]);
      if (isFinite(v)) w[k] = Math.max(0, v - sh.minBid);
    });
    return pricesFromWeights(w, league);
  }

  // A published rank (FantasyPros ECR, ADP) has no dollars: the player at
  // rank r takes the r-th highest dollar value of a reference curve (a dollar
  // list from any source, e.g. ESPN's published values). rankMap {key: rank}.
  function rankImpliedDollars(rankMap, curveDollars) {
    var curve = curveDollars.slice().sort(function (a, b) { return b - a; });
    var keys = Object.keys(rankMap).sort(function (a, b) { return rankMap[a] - rankMap[b]; });
    var out = {};
    keys.forEach(function (k, i) { if (i < curve.length) out[k] = curve[i]; });
    return out;
  }

  // Snake rank: order by draft value, ties broken by key.
  function snakeRanks(values) {
    var out = {};
    sortedKeys(values).forEach(function (k, i) { out[k] = i + 1; });
    return out;
  }

  // Average of several dollar maps (market = FantasyPros + other sources).
  function blendDollars(maps) {
    var sum = {}, cnt = {};
    maps.forEach(function (m) {
      Object.keys(m).forEach(function (k) {
        var v = Number(m[k]);
        if (!isFinite(v)) return;
        sum[k] = (sum[k] || 0) + v; cnt[k] = (cnt[k] || 0) + 1;
      });
    });
    var out = {};
    Object.keys(sum).forEach(function (k) { out[k] = sum[k] / cnt[k]; });
    return out;
  }

  // --------------------------------------------------------- live auction
  // state = {league, me: teamId, teams: [{id, budgetLeft, open}], available:
  //   [playerKey], pos: {playerKey: pos}, prices: {ours, market, platform}}
  // open is per-slot counts {QB, RB, WR, TE, FLEX, SUPERFLEX, K, DST, BN}
  // (a plain count cannot tell K/DST slots from valued ones, so it is
  // refused). Any other key (IR, taxi) is not a draft slot and is ignored.
  // prices are pre-draft league dollars.
  var ROSTER_SLOTS = SKILL_POSITIONS.concat(MIN_BID_POSITIONS, ["FLEX", "SUPERFLEX", "BN"]);
  function openSlots(open) {
    if (!open || typeof open !== "object") throw new Error("open must be per-slot counts, e.g. {QB: 1, BN: 3}");
    return open;
  }
  function slotCount(open, keys) {
    var o = openSlots(open);
    return keys.reduce(function (t, k) { return t + Math.max(0, Math.floor(Number(o[k]) || 0)); }, 0);
  }
  function openCount(open) { return slotCount(open, ROSTER_SLOTS); }
  function openMinBidSlots(open) { return slotCount(open, MIN_BID_POSITIONS); }

  function canRoster(team, pos) {
    var o = openSlots(team.open);
    var has = function (k) { return (Number(o[k]) || 0) > 0; };
    if (has(pos) || has("BN")) return true;
    if (["RB", "WR", "TE"].indexOf(pos) !== -1 && has("FLEX")) return true;
    return SKILL_POSITIONS.indexOf(pos) !== -1 && has("SUPERFLEX");
  }

  // Most a team can bid and still fill every other open slot at the minimum.
  function maxBid(team, league) {
    var minBid = leagueShape(league).minBid;
    var open = openCount(team.open);
    return open > 0 ? team.budgetLeft - minBid * (open - 1) : 0;
  }

  // Inflation for one price map: surplus dollars still in the room divided
  // by surplus value still on the board, where value counts only the best
  // available players who will fill the open valued slots (K and DST slots
  // are minimum-bid slots). factor 1.25 = every remaining player costs 25%
  // more above the minimum than his pre-draft price.
  function inflation(state, priceMap) {
    var league = state.league;
    var minBid = leagueShape(league).minBid;
    var moneyLeft = 0, openTotal = 0, openValued = 0;
    state.teams.forEach(function (t) {
      var o = openCount(t.open);
      moneyLeft += t.budgetLeft; openTotal += o; openValued += o - openMinBidSlots(t.open);
    });
    var surplusLeft = moneyLeft - openTotal * minBid;
    var avail = state.available.filter(function (k) {
      return MIN_BID_POSITIONS.indexOf(state.pos[k]) === -1 && isFinite(priceMap[k]);
    }).sort(function (a, b) { return priceMap[b] - priceMap[a] || (a < b ? -1 : 1); });
    var valueLeft = avail.slice(0, openValued).reduce(function (t, k) {
      return t + Math.max(0, priceMap[k] - minBid);
    }, 0);
    var factor = valueLeft > 0 ? surplusLeft / valueLeft : null;
    // Personal factor: our surplus dollars against our fair share of the
    // value left (value left x our share of the open valued slots). Equal to
    // the room factor while we hold an average share of money per slot;
    // higher when rivals have spent faster than us, so unspent cash raises
    // our bids instead of going to waste.
    var personal = null;
    if (state.me != null && factor != null) {
      var mine = teamById(state, state.me);
      var myOpen = openCount(mine.open), myValued = myOpen - openMinBidSlots(mine.open);
      var mySurplus = mine.budgetLeft - myOpen * minBid;
      personal = myValued > 0 && openValued > 0 ? mySurplus / (valueLeft * myValued / openValued) : null;
    }
    return { moneyLeft: moneyLeft, openSlots: openTotal, openValuedSlots: openValued,
      surplusLeft: surplusLeft, valueLeft: valueLeft, factor: factor,
      inflation: factor == null ? null : factor - 1, personalFactor: personal };
  }

  function inflatedPrice(price, factor, minBid) {
    if (!isFinite(price) || price <= 0 || factor == null) return null;
    return minBid + Math.max(0, price - minBid) * factor;
  }

  function teamById(state, id) {
    for (var i = 0; i < state.teams.length; i += 1) if (state.teams[i].id === id) return state.teams[i];
    throw new Error("no team " + id);
  }

  // The board row for one available player. All bids are whole dollars.
  //   walkAway: the most we pay = our inflated price rounded down, capped at
  //     our max bid and at the best rival max bid (among rivals who can
  //     roster him) + $1, since no rival can force us higher. $1 when he is
  //     outside our priced pool but we have a slot; 0 when we have no slot.
  //   pushFloor: the highest bid we make on a player to make another team
  //     pay (docs/draft-tool/engine.md "Push floor"): the lowest of
  //       (a) walkAway: if nobody tops us we own him at a price we accept;
  //       (b) market clearing price - 1: below the price the room is
  //           expected to pay, so a rival still tops us;
  //       (c) the best rival max bid - 1 among rivals with a slot for him:
  //           someone must be able to top us.
  //     null when that is below the minimum bid (do not push).
  function boardRow(state, key, cache) {
    var league = state.league;
    var minBid = leagueShape(league).minBid;
    var c = cache || boardCache(state);
    var me = teamById(state, state.me);
    var pos = state.pos[key];
    var p = state.prices;
    var ours = p.ours ? p.ours[key] : undefined;
    var market = p.market ? p.market[key] : undefined;
    var platform = p.platform ? p.platform[key] : undefined;
    // state.ourFactor: "room" (default; the hand-checked worked example) or
    // "personal" (our money share vs slot share; see inflation()).
    var ourFactor = state.ourFactor === "personal" && c.ours.personalFactor != null
      ? c.ours.personalFactor : c.ours.factor;
    var oursInfl = inflatedPrice(ours, ourFactor, minBid);
    var marketInfl = c.market ? inflatedPrice(market, c.market.factor, minBid) : null;
    var platformInfl = c.platform ? inflatedPrice(platform, c.platform.factor, minBid) : null;
    var myMax = maxBid(me, league);
    var rivalCeiling = 0;
    state.teams.forEach(function (t) {
      if (t.id !== state.me && canRoster(t, pos)) rivalCeiling = Math.max(rivalCeiling, maxBid(t, league));
    });
    var walkAway = 0;
    if (canRoster(me, pos) && myMax >= minBid) {
      var own = oursInfl != null ? Math.floor(oursInfl + EPS) : minBid;
      walkAway = Math.max(minBid, Math.min(myMax, own, rivalCeiling + minBid));
    }
    var pushFloor = null;
    if (walkAway >= minBid && marketInfl != null) {
      var b = Math.min(walkAway, Math.floor(marketInfl + EPS) - 1, rivalCeiling - 1);
      pushFloor = b >= minBid ? b : null;
    }
    return { key: key, pos: pos, ours: ours, market: market, platform: platform,
      oursInflated: oursInfl, marketInflated: marketInfl, platformInflated: platformInfl,
      walkAway: walkAway, pushFloor: pushFloor, myMaxBid: myMax, rivalCeiling: rivalCeiling };
  }

  function boardCache(state) {
    var p = state.prices;
    return { ours: inflation(state, p.ours || {}),
      market: p.market ? inflation(state, p.market) : null,
      platform: p.platform ? inflation(state, p.platform) : null };
  }

  // Whole board: inflation per price, max bid per team, a row per player.
  function board(state) {
    var cache = boardCache(state);
    var maxBids = {};
    state.teams.forEach(function (t) { maxBids[t.id] = maxBid(t, state.league); });
    return { version: VERSION, inflation: cache, maxBids: maxBids,
      rows: state.available.map(function (k) { return boardRow(state, k, cache); }) };
  }

  // ------------------------------------------------------ opponent model
  // docs/draft-tool/engine.md "Push floor, thought through" and
  // research-nominations-opponents.md. Estimates only: a rival's real limit
  // is unknown, so each estimate carries a relative spread (sigma).
  var OPPONENT_DEFAULTS = {
    benchNeed: 0.6,        // need factor when only a bench slot fits him
    sigma: 0.2,            // relative spread of a rival's limit around the estimate
    platformBlend: 0.5,    // room price = market x (1 - blend) + platform x blend
    benchStuckFactor: 0.5, // our value of a bench-only player, share of his price
    targetMargin: 2,       // $ over the clearing price that makes him a target
    drainWeight: 0.5,      // what a rival dollar drained is worth to us (candidate C)
    stuckAllowance: 1      // most expected $ loss we accept on one push (candidate C)
  };

  // 1 when a starting slot (his position, FLEX, SUPERFLEX) is open for him,
  // benchNeed when only the bench fits, 0 when nothing does.
  function needFactor(team, pos, opts) {
    var o = openSlots(team.open);
    var has = function (k) { return (Number(o[k]) || 0) > 0; };
    if (has(pos)) return 1;
    if (["RB", "WR", "TE"].indexOf(pos) !== -1 && has("FLEX")) return 1;
    if (SKILL_POSITIONS.indexOf(pos) !== -1 && has("SUPERFLEX")) return 1;
    if (has("BN")) return (opts || OPPONENT_DEFAULTS).benchNeed;
    return 0;
  }

  function normCdf(z) { return 0.5 * (1 + ValueModel.esErf(z / Math.SQRT2)); }

  // The room's price for a player now and every rival's estimated limit.
  // tendency(teamId, pos) -> multiplier (league tendencies; default 1).
  function opponentModel(state, key, options) {
    var opts = Object.assign({}, OPPONENT_DEFAULTS, options || {});
    var league = state.league;
    var minBid = leagueShape(league).minBid;
    var c = (options && options.cache) || boardCache(state);
    var pos = state.pos[key];
    var p = state.prices;
    var m = c.market ? inflatedPrice(p.market && p.market[key], c.market.factor, minBid) : null;
    var pl = c.platform ? inflatedPrice(p.platform && p.platform[key], c.platform.factor, minBid) : null;
    var room = m != null && pl != null ? m * (1 - opts.platformBlend) + pl * opts.platformBlend : (m != null ? m : pl);
    var rivals = [];
    state.teams.forEach(function (t) {
      if (t.id === state.me) return;
      var need = needFactor(t, pos, opts);
      var mb = maxBid(t, league);
      if (need <= 0 || mb < minBid) return;
      var tend = opts.tendency ? opts.tendency(t.id, pos) : 1;
      var est = room == null ? minBid : Math.min(mb, Math.max(minBid, room * need * tend));
      rivals.push({ id: t.id, need: need, maxBid: mb, estimate: est });
    });
    rivals.sort(function (a, b) { return b.estimate - a.estimate || b.maxBid - a.maxBid; });
    var w1 = rivals.length ? rivals[0].estimate : 0;
    var w2 = rivals.length > 1 ? rivals[1].estimate : (rivals.length ? minBid : 0);
    var clearing = rivals.length ? Math.min(w1, w2 + minBid) : null;
    return { pos: pos, roomPrice: room, rivals: rivals, w1: w1, w2: w2, clearing: clearing,
      topRivalMaxBid: rivals.length ? rivals[0].maxBid : 0, opts: opts };
  }

  // Our value of him to our roster as it stands: his inflated price when he
  // starts for us, benchStuckFactor of it when only the bench fits, 0 when
  // nothing fits.
  function rosterValue(state, key, model, cache) {
    var me = teamById(state, state.me);
    var row = boardRow(state, key, cache);
    var need = needFactor(me, state.pos[key], { benchNeed: model.opts.benchStuckFactor });
    var v = row.oursInflated == null ? 0 : row.oursInflated * need;
    return { value: v, buyLimit: Math.min(row.walkAway, Math.floor(v + EPS)), row: row };
  }

  // Push floor candidates for one player (engine.md "Push floor, thought
  // through"). Returns the classification (target / neutral / fade /
  // uncontested: cost to win = best rival limit + $1 against our roster
  // value), our buy limit and the push floor under each candidate:
  //   A  lowest of walk-away, market - $1, best rival max - $1 (first draft)
  //   B  our roster value: the most we are glad to own him at (buy limit)
  //   C  B, plus a bounded overreach on fades and neutrals: the bid above B
  //      that maximises drained rival dollars x drainWeight minus expected
  //      stuck loss, keeping expected loss <= stuckAllowance
  function pushFloors(state, key, options) {
    var cache = (options && options.cache) || boardCache(state);
    var model = opponentModel(state, key, Object.assign({}, options, { cache: cache }));
    var opts = model.opts;
    var minBid = leagueShape(state.league).minBid;
    var rv = rosterValue(state, key, model, cache);
    var row = rv.row;
    var me = teamById(state, state.me);
    var myMax = maxBid(me, state.league);
    var canBid = canRoster(me, model.pos) && myMax >= minBid;
    var costToWin = model.rivals.length ? model.w1 + minBid : minBid;
    var cls = !model.rivals.length ? "uncontested"
      : rv.value >= costToWin + opts.targetMargin ? "target"
      : rv.value <= costToWin - opts.targetMargin ? "fade" : "neutral";
    var cap = Math.min(myMax, model.topRivalMaxBid - minBid);
    var a = row.pushFloor;
    var base = canBid && rv.buyLimit >= minBid ? rv.buyLimit : null;
    var cBest = base, cDetail = null;
    if (canBid && model.rivals.length && cls !== "target") {
      var sd = Math.max(1, opts.sigma * model.w1);
      var from = base == null ? 0 : base;
      var best = 0;
      for (var bid = Math.max(minBid, from + 1); bid <= cap; bid += 1) {
        var pStuck = normCdf((bid - model.w1) / sd);
        var drain = Math.max(0, bid - Math.max(from, model.w2));
        var loss = Math.max(0, bid - rv.value);
        var expLoss = pStuck * loss;
        if (expLoss > opts.stuckAllowance + EPS) break;
        var gain = (1 - pStuck) * drain * opts.drainWeight - expLoss;
        if (gain > best + EPS) { best = gain; cBest = bid; cDetail = { pStuck: pStuck, drain: drain, expectedLoss: expLoss, gain: gain }; }
      }
    }
    return { key: key, classification: cls, costToWin: costToWin, clearing: model.clearing,
      w1: model.w1, w2: model.w2, rosterValue: rv.value, buyLimit: rv.buyLimit, walkAway: row.walkAway,
      pushFloor: { A: a, B: base, C: cBest }, candidateC: cDetail, rivals: model.rivals.length,
      roomPrice: model.roomPrice };
  }

  // Nomination plays (research-nominations-opponents.md), ranked:
  //   uncontested  a target at most one rival can chase now
  //   drain        a fade two or more needy rivals will bid past our value
  //   endgame      every rival is down to a $1-$2 max bid: our best target
  //   discovery    otherwise the priciest player we do not need to win
  // Scores are in dollars. Returns up to `limit` suggestions.
  function nominationPlays(state, options) {
    var opts = Object.assign({ limit: 3, scan: 120 }, options || {});
    var cache = boardCache(state);
    var minBid = leagueShape(state.league).minBid;
    var me = teamById(state, state.me);
    var rivalsMax = 0;
    state.teams.forEach(function (t) { if (t.id !== state.me) rivalsMax = Math.max(rivalsMax, maxBid(t, state.league)); });
    var room = state.prices.market || state.prices.ours;
    var keys = state.available.filter(function (k) { return canRoster(me, state.pos[k]); })
      .sort(function (a, b) { return (room[b] || 0) - (room[a] || 0) || (a < b ? -1 : 1); }).slice(0, opts.scan);
    var plays = [];
    keys.forEach(function (k) {
      var pf = pushFloors(state, k, Object.assign({}, opts, { cache: cache }));
      var needy = 0;
      opponentModel(state, k, Object.assign({}, opts, { cache: cache })).rivals.forEach(function (r) {
        if (r.need >= 1 && r.estimate >= pf.buyLimit) needy += 1;
      });
      if (rivalsMax <= 2 * minBid && pf.buyLimit >= minBid) {
        plays.push({ key: k, play: "endgame", score: 100 + pf.rosterValue, detail: pf });
      } else if ((pf.classification === "target" || pf.classification === "uncontested") && needy <= 1) {
        plays.push({ key: k, play: "uncontested", score: 50 + pf.rosterValue - pf.costToWin, detail: pf });
      } else if (pf.classification === "fade" && needy >= 2 && pf.clearing >= pf.buyLimit + 3) {
        plays.push({ key: k, play: "drain", score: 25 + pf.clearing - pf.buyLimit, detail: pf });
      } else if (pf.classification !== "target") {
        plays.push({ key: k, play: "discovery", score: (pf.roomPrice || 0) / 10, detail: pf });
      }
    });
    plays.sort(function (a, b) { return b.score - a.score || (a.key < b.key ? -1 : 1); });
    return plays.slice(0, opts.limit);
  }

  var DraftEngine = {
    VERSION: VERSION,
    SCORING_PRESETS: SCORING_PRESETS,
    VEGAS_MARKETS: VEGAS_MARKETS,
    fantasyPoints: fantasyPoints,
    vegasStatLine: vegasStatLine,
    leagueShape: leagueShape,
    pipelineSetting: pipelineSetting,
    preseasonLineup: preseasonLineup,
    DRAFT_BASIS_WEIGHTS: DRAFT_BASIS_WEIGHTS,
    draftBasisConfig: draftBasisConfig,
    ddfDraftValues: ddfDraftValues,
    pricesFromWeights: pricesFromWeights,
    ourPrices: ourPrices,
    rescaleDollars: rescaleDollars,
    rankImpliedDollars: rankImpliedDollars,
    blendDollars: blendDollars,
    snakeRanks: snakeRanks,
    canRoster: canRoster,
    maxBid: maxBid,
    inflation: inflation,
    inflatedPrice: inflatedPrice,
    boardRow: boardRow,
    board: board,
    OPPONENT_DEFAULTS: OPPONENT_DEFAULTS,
    needFactor: needFactor,
    opponentModel: opponentModel,
    rosterValue: rosterValue,
    pushFloors: pushFloors,
    nominationPlays: nominationPlays
  };
  root.DraftEngine = DraftEngine;
  if (typeof module !== "undefined" && module.exports) module.exports = DraftEngine;
})(typeof globalThis !== "undefined" ? globalThis : this);
