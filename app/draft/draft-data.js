// DDF draft tool data layer, Phase 1 (JEG-1667). Reads the recurring data
// that is the same for every league (Jeremy, 2026-11-27: "pulled in
// supabase") and shapes it into one bundle. League math stays in
// draft-core.js and draft-engine.js, client side. Pure except loadSupabase.
//
// DraftData.loadSupabase({fetch, namesUrl}) -> Promise<bundle>
//   Public-read tables only, with the project's publishable key (not a
//   secret): draft_pulls, draft_market_latest, fp_season_projections,
//   draft_vegas_lines (else vegas_season_totals). Nothing is written.
// DraftData.assemble(raw) -> bundle (pure; raw = the rows of those tables
//   plus names: the player table rows "Name|POS|TEAM|player_key")
// DraftData.staleness(bundle, now) -> {stale, hours, pullDate, label}
//
// bundle = {v: 1, season, asOf: {pullDate, pulledAt, sources: {source:
//   {pullDate, pulledAt, sourceUpdatedAt}}, projections, vegas, vegasSource},
//   credits: [text], players: [{key, name, pos, team, bye, proj, vegas,
//   ecr: {STD|HALF|PPR: {rank, tier, sd}}, espn: {STD, PPR, aav}}],
//   dropped: {unnamedProjections, vegasUnmatched}}
// A player's key is his projection player_key when he has a projection,
// else "fp:<FantasyPros id>" or "espn:<ESPN id>".
(function (root) {
  "use strict";

  var CONFIG = {
    url: "https://iskiybsimubiujwuchsl.supabase.co",
    // Supabase publishable key: public by design, read-only through RLS.
    key: "sb_publishable_pzHxlyPf-jZFpStnejUUsQ_OaYuj4j7"
  };
  var SKILL = ["QB", "RB", "WR", "TE"];
  var STALE_HOURS = 25; // "older than a day", with an hour for the daily job to finish
  var STAT_COLUMNS = {
    pass_yds: "passing_yards", pass_tds: "passing_tds", ints: "interceptions",
    rush_yds: "rushing_yards", rush_tds: "rushing_tds", rec: "receptions",
    rec_yds: "receiving_yards", rec_tds: "receiving_tds", fum_lost: "fumbles_lost"
  };
  // Nicknames a source spells differently (same list as tools/draft_backtest.mjs).
  var NAME_ALIASES = { "kenny gainwell": "kenneth gainwell" };

  function normName(s) {
    var n = String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[.'’]/g, "").replace(/-/g, " ").replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "")
      .replace(/\s+/g, " ").trim();
    return NAME_ALIASES[n] || n;
  }
  function normPos(p) {
    var u = String(p || "").toUpperCase();
    return u === "DEF" || u === "D/ST" ? "DST" : u;
  }
  function numOrNull(x) {
    if (x === null || x === undefined || x === "") return null;
    var v = Number(x);
    return isFinite(v) ? v : null;
  }

  function latestPulls(pulls) {
    var out = {};
    (pulls || []).forEach(function (p) {
      if (p.status !== "ok") return;
      var cur = out[p.source];
      if (!cur || String(p.pull_date) > String(cur.pullDate)) {
        out[p.source] = { pullDate: String(p.pull_date), pulledAt: p.pulled_at || null,
          sourceUpdatedAt: p.source_updated_at || null, season: p.season };
      }
    });
    return out;
  }

  function assemble(raw) {
    var sources = latestPulls(raw.pulls);
    var names = {};
    (raw.names || []).forEach(function (row) {
      var f = String(row).split("|");
      if (f[3]) names[f[3]] = { name: f[0], pos: f[1], team: f[2] };
    });

    var players = [], byKey = {}, byName = {};
    function add(p) {
      players.push(p); byKey[p.key] = p;
      var nk = normName(p.name) + "|" + p.pos;
      if (!byName[nk]) byName[nk] = p;
      return p;
    }
    function blank(key, name, pos, team) {
      return { key: String(key), name: name, pos: pos, team: team || "", bye: null, proj: null, vegas: null, ecr: {}, espn: {} };
    }

    // Projections: one row per player for the latest snapshot.
    var unnamed = [];
    (raw.projections || []).forEach(function (r) {
      var key = String(r.player_key), pos = normPos(r.position);
      if (SKILL.indexOf(pos) === -1) return;
      var proj = {};
      Object.keys(STAT_COLUMNS).forEach(function (k) { var v = numOrNull(r[STAT_COLUMNS[k]]); proj[k] = v === null ? 0 : v; });
      var nm = names[key];
      if (!nm) { unnamed.push({ key: key, pos: pos, team: r.team || "", proj: proj }); return; }
      add(blank(key, nm.name, pos, r.team || nm.team)).proj = proj;
    });

    // Market rows: FantasyPros ECR (rank, tier, bye) and ESPN (dollars, AAV).
    var orphans = {}; // market players with no projection, by source id
    (raw.market || []).forEach(function (m) {
      var pos = normPos(m.pos);
      if (SKILL.concat(["K", "DST"]).indexOf(pos) === -1) return;
      var p = byName[normName(m.player_name) + "|" + pos];
      if (!p) {
        var prefix = m.source === "espn" ? "espn:" : "fp:";
        // The same player from the other source joins on name and position.
        p = add(blank(prefix + m.source_player_id, m.player_name, pos, m.team));
        orphans[p.key] = p;
      }
      if (m.source === "fantasypros_ecr") {
        p.ecr[m.scoring] = { rank: numOrNull(m.rank_overall), tier: numOrNull(m.tier), sd: numOrNull(m.rank_sd) };
        if (p.bye === null) p.bye = numOrNull(m.bye);
        if (!p.team && m.team) p.team = m.team;
      } else if (m.source === "espn") {
        var d = numOrNull(m.dollars);
        if (d !== null) p.espn[m.scoring] = d;
        var aav = numOrNull(m.aav);
        if (aav !== null) p.espn.aav = aav;
      }
    });

    // A projection row with no name in the player table is named by the one
    // market-only skill player of the same position and team, when exactly
    // one fits; otherwise it is left out and counted (never guessed).
    var droppedUnnamed = 0;
    unnamed.forEach(function (u) {
      var fits = Object.keys(orphans).map(function (k) { return orphans[k]; }).filter(function (o) {
        return o.pos === u.pos && o.team && o.team === u.team && !o.proj;
      });
      if (fits.length !== 1) { droppedUnnamed += 1; return; }
      var o = fits[0];
      delete byKey[o.key]; delete orphans[o.key];
      o.key = u.key; o.proj = u.proj; byKey[o.key] = o;
    });

    // Vegas season props: one line per player and market. Two books for the
    // same market are averaged (both are Vegas; no source is mixed in).
    var vegasRows = raw.vegas || [], vegasUnmatched = 0, sums = {};
    vegasRows.forEach(function (v) {
      var line = numOrNull(v.line);
      if (line === null) return;
      var p = v.player_key != null ? byKey[String(v.player_key)] : null;
      if (!p) {
        var nk = normName(v.player_name);
        for (var i = 0; i < SKILL.length && !p; i += 1) p = byName[nk + "|" + SKILL[i]] || null;
      }
      if (!p) { vegasUnmatched += 1; return; }
      var id = p.key + "|" + v.market;
      sums[id] = sums[id] || { p: p, market: v.market, total: 0, n: 0 };
      sums[id].total += line; sums[id].n += 1;
    });
    Object.keys(sums).forEach(function (id) {
      var s = sums[id];
      s.p.vegas = s.p.vegas || {};
      s.p.vegas[s.market] = s.total / s.n;
    });

    var pullDates = Object.keys(sources).map(function (s) { return sources[s].pullDate; }).sort();
    var pulledAts = Object.keys(sources).map(function (s) { return sources[s].pulledAt; }).filter(Boolean).sort();
    var credits = {};
    (raw.market || []).forEach(function (m) { if (m.credit) credits[m.credit] = 1; });
    var seasons = Object.keys(sources).map(function (s) { return sources[s].season; });
    return {
      v: 1,
      season: raw.season || seasons[0] || null,
      asOf: { pullDate: pullDates[0] || null, pulledAt: pulledAts[0] || null, sources: sources,
        projections: raw.projectionSnapshot || null, vegas: raw.vegasSnapshot || null, vegasSource: raw.vegasSource || null },
      credits: Object.keys(credits).sort(),
      players: players,
      dropped: { unnamedProjections: droppedUnnamed, vegasUnmatched: vegasUnmatched }
    };
  }

  // The oldest source decides: the board is only as fresh as its stalest input.
  function staleness(bundle, now) {
    var asOf = (bundle && bundle.asOf) || {};
    var at = asOf.pulledAt ? Date.parse(asOf.pulledAt) : (asOf.pullDate ? Date.parse(asOf.pullDate + "T00:00:00Z") : NaN);
    if (!isFinite(at)) return { stale: true, hours: null, pullDate: null, label: "No pull found" };
    var t = now == null ? Date.now() : (typeof now === "number" ? now : Date.parse(now));
    var hours = (t - at) / 3600000;
    return { stale: hours > STALE_HOURS, hours: hours, pullDate: asOf.pullDate,
      label: "Updated " + asOf.pullDate };
  }

  function getAll(f, path) {
    var out = [], page = 1000;
    function next(offset) {
      var sep = path.indexOf("?") === -1 ? "?" : "&";
      return f(CONFIG.url + "/rest/v1/" + path + sep + "limit=" + page + "&offset=" + offset,
        { headers: { apikey: CONFIG.key } }).then(function (r) {
        if (!r.ok) throw new Error("data " + path.split("?")[0] + ": HTTP " + r.status);
        return r.json();
      }).then(function (rows) {
        out = out.concat(rows);
        return rows.length === page ? next(offset + page) : out;
      });
    }
    return next(0);
  }

  function getFirst(f, path) {
    return f(CONFIG.url + "/rest/v1/" + path + "&limit=1", { headers: { apikey: CONFIG.key } }).then(function (r) {
      if (!r.ok) throw new Error("data " + path.split("?")[0] + ": HTTP " + r.status);
      return r.json();
    });
  }

  function loadSupabase(opts) {
    var o = opts || {};
    var f = o.fetch || root.fetch.bind(root);
    var raw = {};
    return getAll(f, "draft_pulls?select=pull_date,source,season,status,source_updated_at,pulled_at&status=eq.ok&order=pull_date.desc,source").then(function (pulls) {
      raw.pulls = pulls.slice(0, 20);
      raw.season = pulls.length ? pulls[0].season : null;
      return getAll(f, "draft_market_latest?select=source,scoring,source_player_id,player_name,pos,team,bye,rank_overall,tier,rank_sd,dollars,aav,credit&order=source,scoring,source_player_id");
    }).then(function (market) {
      raw.market = market;
      return getFirst(f, "fp_season_projections?select=snapshot_date&season=eq." + raw.season + "&order=snapshot_date.desc");
    }).then(function (snaps) {
      raw.projectionSnapshot = snaps.length ? snaps[0].snapshot_date : null;
      if (!raw.projectionSnapshot) return [];
      var cols = ["player_key", "position", "team"].concat(Object.keys(STAT_COLUMNS).map(function (k) { return STAT_COLUMNS[k]; }));
      return getAll(f, "fp_season_projections?select=" + cols.join(",") + "&season=eq." + raw.season +
        "&snapshot_date=eq." + raw.projectionSnapshot + "&order=player_key");
    }).then(function (proj) {
      raw.projections = proj;
      return getAll(f, "draft_vegas_lines?select=snapshot_date,player_key,player_name,market,line&season=eq." + raw.season + "&order=snapshot_date.desc,player_key,market");
    }).then(function (pasted) {
      if (pasted.length) {
        raw.vegasSnapshot = pasted[0].snapshot_date; raw.vegasSource = "paste";
        return pasted.filter(function (r) { return r.snapshot_date === raw.vegasSnapshot; });
      }
      return getAll(f, "vegas_season_totals?select=snapshot_date,player_name,market,line,book&season=eq." + raw.season + "&order=snapshot_date.desc,player_name,market,book").then(function (rows) {
        raw.vegasSnapshot = rows.length ? rows[0].snapshot_date : null; raw.vegasSource = rows.length ? "books" : null;
        return rows.filter(function (r) { return r.snapshot_date === raw.vegasSnapshot; });
      });
    }).then(function (vegas) {
      raw.vegas = vegas;
      return f(o.namesUrl || "../next/players-table-1.json").then(function (r) {
        if (!r.ok) throw new Error("player table: HTTP " + r.status);
        return r.json();
      });
    }).then(function (names) {
      raw.names = names;
      return assemble(raw);
    });
  }

  var DraftData = { CONFIG: CONFIG, STALE_HOURS: STALE_HOURS, normName: normName, assemble: assemble,
    staleness: staleness, loadSupabase: loadSupabase };
  root.DraftData = DraftData;
  if (typeof module !== "undefined" && module.exports) module.exports = DraftData;
})(typeof globalThis !== "undefined" ? globalThis : this);
