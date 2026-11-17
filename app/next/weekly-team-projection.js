/* Weekly team projection (JEG-1658, part of JEG-1653). Doc: docs/weekly-team-projection.md.
 * For each team in a league-state/1 document and each week in the window, the expected points of the best legal
 * lineup (the league's starter slots, FLEX and SUPER_FLEX included) from that week's projections. Pure: no fetch, no
 * clock, no DOM. Weekly-only: nothing here reads or feeds DDF Value, rest-of-season values, charts or the pipeline.
 *
 * Rules (Jeremy 2026-11-16):
 * - Primary source Sleeper, points as Sleeper gives them for the league's format. The points come from ONE function
 *   (opts.points, default providerPoints) so per-league rescoring from stat lines (JEG-1688) replaces it alone.
 * - ESPN is computed the same way as a cross-check and shown beside the Sleeper figure, never blended.
 * - A player on bye (nflverse schedule: his team has no game that week) does not play.
 * - A player listed out does not play before his expected return week; from it on he counts, flagged uncertain.
 *   A weekly "Out" with no return week given is out for that report week only. IR/PUP/NFI/suspended with no return
 *   week uses the provider's weeks as given (zero = out), flagged uncertain.
 * - A player with no projection for a week is null with a reason and the next player fills in. A week the source has
 *   no rows for at all is null with a reason for every team. Missing is never zero; a provider's 0 is a value.
 * - Week 18 carries a "teams may rest starters" flag. No betting lines.
 *
 * DDF.weeklyTeamProjection.project(state, inputs, opts) -> {version, ok, reason, window, basis, sources, teams}
 *   state:  league-state/1 (DDF.leagueState)
 *   inputs: {rosters: {teamId: [sleeper player id]}, slots: [Sleeper roster_positions], scoring: ppr|half_ppr|standard,
 *            projections: [warehouse source_weekly_projections rows], schedule: [{week, home_team, away_team}] | null,
 *            injuries: [{sleeper_id, status, week?, return_week?, source?}], players?: {id: [name, pos, team]}}
 *   opts:   {fromWeek, lastWeek, primary: "sleeper", crossCheck: "espn" | null, points(row, ctx) -> number | null}
 * DDF.weeklyTeamProjection.providerPoints(row, ctx)  the stored points_<format> (the JEG-1688 swap point)
 * DDF.weeklyTeamProjection.bestLineup(slots, players) -> {points, lineup, empty_slots} (exact assignment)
 * DDF.weeklyTeamProjection.slotsFromSettings(settings) -> roster_positions from DDF settings {roster, superflex, superflexSlots}
 * DDF.weeklyTeamProjection.rostersFromSleeper(rosters) -> {roster_id: [player ids]} (taxi squad left out)
 * DDF.weeklyTeamProjection.window(state, opts)       -> {from, last, weeks, source, reason}
 */
(function (root) {
  "use strict";
  var VERSION = "weekly-team-projection/1";
  var LAST_NFL_WEEK = 18;   /* Sleeper offers no skill-position weeks 19+; week 18 is when teams may rest starters */
  var POSITIONS = ["QB", "RB", "WR", "TE"];
  var ELIGIBLE = {
    QB: ["QB"], RB: ["RB"], WR: ["WR"], TE: ["TE"],
    FLEX: ["RB", "WR", "TE"], WRRB_FLEX: ["RB", "WR"], REC_FLEX: ["WR", "TE"], WRTE_FLEX: ["WR", "TE"], RBTE_FLEX: ["RB", "TE"],
    SUPER_FLEX: ["QB", "RB", "WR", "TE"]
  };
  var NOT_STARTERS = ["BN", "IR", "TAXI"];
  var LONG_OUT = ["ir", "pup", "nfi", "sus", "suspended", "injured reserve", "reserve"];
  var FORMAT_COLUMN = {ppr: "points_ppr", half_ppr: "points_half_ppr", standard: "points_std"};
  var SOURCE_LABEL = {sleeper: "Sleeper", espn: "ESPN", cbs: "CBS"};
  /* nflverse team codes are the reference; Sleeper and ESPN spell a few differently */
  var TEAM_ALIAS = {LAR: "LA", STL: "LA", JAC: "JAX", WSH: "WAS", LVR: "LV", OAK: "LV", SD: "LAC"};
  var BIG = 1e6;

  function num(x) {
    if (typeof x === "number") return isFinite(x) ? x : null;
    if (typeof x === "string" && x.trim() !== "" && isFinite(Number(x))) return Number(x);
    return null;
  }
  function isWhole(x, lo, hi) { return typeof x === "number" && isFinite(x) && Math.floor(x) === x && x >= lo && x <= hi; }
  function round2(x) { return Math.round(x * 100) / 100; }
  function teamCode(t) { var s = typeof t === "string" ? t.trim().toUpperCase() : ""; return s ? (TEAM_ALIAS[s] || s) : null; }
  function label(src) { return SOURCE_LABEL[src] || src; }
  function cellValue(c) { return c && typeof c === "object" && c.value !== null && c.value !== undefined ? c.value : null; }

  /* The one points function. ctx = {scoring, source, week}. JEG-1688 replaces this with a rescore of row.stats under
     the league's own scoring settings; nothing else in this module reads points. */
  function providerPoints(row, ctx) {
    var col = FORMAT_COLUMN[ctx && ctx.scoring];
    return col ? num(row[col]) : null;
  }

  function directSleeperId(row) {
    if (row.sleeper_id !== null && row.sleeper_id !== undefined && String(row.sleeper_id) !== "") return String(row.sleeper_id);
    if (row.source === "sleeper" && row.source_player_id) return String(row.source_player_id);
    return null;
  }

  /* projections -> {bySource: {source: {byWeek: {week: {playerId: row}}, weeks: {week: true}, as_of, basis, unmatched}},
     teamOf: {playerId: team}} keeping the newest as_of when a player-week repeats (callers pass the latest run only) */
  function indexProjections(rows) {
    var out = Object.create(null), teamOf = Object.create(null), teamKey = Object.create(null);
    /* ESPN rows mostly have no sleeper_id (74% on 2026-11-16) but all have player_key; the Sleeper rows give the
       player_key -> Sleeper id crosswalk, so the cross-check joins through it */
    var keyToSid = Object.create(null);
    (Array.isArray(rows) ? rows : []).forEach(function (r) {
      var sid = r ? directSleeperId(r) : null;
      if (sid && r.player_key !== null && r.player_key !== undefined) keyToSid[String(r.player_key)] = sid;
    });
    (Array.isArray(rows) ? rows : []).forEach(function (r) {
      if (!r || typeof r.source !== "string" || !isWhole(num(r.target_week), 1, 22)) return;
      var s = out[r.source] || (out[r.source] = {byWeek: Object.create(null), weeks: Object.create(null), as_of: null, basis: null, unmatched: 0});
      var wk = num(r.target_week);
      s.weeks[wk] = true;
      if (r.as_of && (!s.as_of || String(r.as_of) > s.as_of)) s.as_of = String(r.as_of);
      if (r.scoring_basis && !s.basis) s.basis = String(r.scoring_basis);
      var id = directSleeperId(r) || (r.player_key !== null && r.player_key !== undefined ? keyToSid[String(r.player_key)] || null : null);
      if (!id) { s.unmatched++; return; }
      /* the player's team from his newest row in any source and week: a bye week has no Sleeper row to read it from */
      if (r.team) {
        var k = [String(r.as_of || ""), wk], prevK = teamKey[id];
        if (!prevK || k[0] > prevK[0] || (k[0] === prevK[0] && k[1] >= prevK[1])) { teamOf[id] = r.team; teamKey[id] = k; }
      }
      var wkRows = s.byWeek[wk] || (s.byWeek[wk] = Object.create(null));
      var prev = wkRows[id];
      if (!prev || String(r.as_of || "") > String(prev.as_of || "")) wkRows[id] = r;
    });
    return {bySource: out, teamOf: teamOf};
  }

  /* schedule -> {week: {team: true}}; a week with no games listed is unknown (null), not "everyone on bye" */
  function indexSchedule(games) {
    if (!Array.isArray(games)) return null;
    var out = Object.create(null);
    games.forEach(function (g) {
      if (!g || !isWhole(num(g.week), 1, 22)) return;
      if (g.game_type && String(g.game_type).toUpperCase() !== "REG") return;
      var w = out[num(g.week)] || (out[num(g.week)] = Object.create(null));
      [g.home_team, g.away_team].forEach(function (t) { var c = teamCode(t); if (c) w[c] = true; });
    });
    return out;
  }

  function indexInjuries(list) {
    var out = Object.create(null);
    (Array.isArray(list) ? list : []).forEach(function (j) {
      if (!j || j.sleeper_id === null || j.sleeper_id === undefined) return;
      var status = String(j.status || "").trim();
      var s = status.toLowerCase();
      var isOut = s === "out" || LONG_OUT.indexOf(s) >= 0;
      if (!isOut) return;   /* questionable and doubtful play */
      out[String(j.sleeper_id)] = {
        status: status, long: LONG_OUT.indexOf(s) >= 0,
        week: isWhole(num(j.week), 1, 22) ? num(j.week) : null,
        return_week: isWhole(num(j.return_week), 1, 22) ? num(j.return_week) : null,
        source: j.source || null
      };
    });
    return out;
  }

  /* availability of one player in one week, before projections: {out: reason} or {uncertain: reason} or {} */
  function injuryRule(inj, week) {
    if (!inj) return {};
    if (inj.return_week !== null) {
      if (week < inj.return_week) return {out: inj.status + ", expected back week " + inj.return_week};
      return {uncertain: inj.status + " now, expected back week " + inj.return_week};
    }
    if (!inj.long) {
      if (inj.week === null) return {out: inj.status + " on the injury report (report week unknown, so every week)"};
      if (week <= inj.week) return {out: inj.status + " on the week " + inj.week + " injury report"};
      return {uncertain: inj.status + " on the week " + inj.week + " injury report, assumed back after it"};
    }
    return {uncertain: inj.status + " with no expected return week; " + "the provider's weeks are used as given"};
  }

  /* Exact best lineup: assignment of starter slots to players maximising points (Hungarian method). Greedy filling is
     not exact when flex sets overlap without nesting (WRRB_FLEX with REC_FLEX). players: [{id, pos, points}] */
  function bestLineup(slots, players) {
    var starters = (slots || []).filter(function (s) { return ELIGIBLE[s]; });
    var pool = (players || []).filter(function (p) { return p && POSITIONS.indexOf(p.pos) >= 0 && typeof p.points === "number" && isFinite(p.points); })
      .slice().sort(function (a, b) { return b.points - a.points || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0); });
    /* only the top k players at a position can start, k = slots that take that position */
    var cap = {};
    POSITIONS.forEach(function (pos) { cap[pos] = starters.filter(function (s) { return ELIGIBLE[s].indexOf(pos) >= 0; }).length; });
    var seen = {}, cand = [];
    pool.forEach(function (p) { seen[p.pos] = (seen[p.pos] || 0) + 1; if (seen[p.pos] <= cap[p.pos]) cand.push(p); });
    var n = starters.length;
    if (!n) return {points: 0, lineup: [], empty_slots: []};
    var m = cand.length + n;   /* plus one "empty" column per slot, so every slot can be left empty */
    var cost = starters.map(function (s) {
      var row = cand.map(function (p) { return ELIGIBLE[s].indexOf(p.pos) >= 0 ? -p.points : BIG; });
      for (var k = 0; k < n; k++) row.push(1e-6);   /* empty only when no eligible player is left */
      return row;
    });
    var pick = hungarian(cost, n, m);
    var lineup = [], empty = [], total = 0;
    starters.forEach(function (s, i) {
      var j = pick[i];
      var p = j < cand.length && cost[i][j] < BIG ? cand[j] : null;
      if (p) { total += p.points; lineup.push({slot: s, player_id: p.id, pos: p.pos, points: p.points}); }
      else { empty.push(s); lineup.push({slot: s, player_id: null, pos: null, points: null}); }
    });
    return {points: round2(total), lineup: lineup, empty_slots: empty};
  }

  /* minimum-cost assignment, n rows <= m columns; returns the column for each row (e-maxx formulation) */
  function hungarian(cost, n, m) {
    var INF = Infinity, u = [], v = [], p = [], way = [], i, j;
    for (j = 0; j <= m; j++) { v[j] = 0; p[j] = 0; way[j] = 0; }
    for (i = 0; i <= n; i++) u[i] = 0;
    for (i = 1; i <= n; i++) {
      p[0] = i;
      var j0 = 0, minv = [], used = [];
      for (j = 0; j <= m; j++) { minv[j] = INF; used[j] = false; }
      do {
        used[j0] = true;
        var i0 = p[j0], delta = INF, j1 = 0;
        for (j = 1; j <= m; j++) {
          if (used[j]) continue;
          var cur = cost[i0 - 1][j - 1] - u[i0] - v[j];
          if (cur < minv[j]) { minv[j] = cur; way[j] = j0; }
          if (minv[j] < delta) { delta = minv[j]; j1 = j; }
        }
        for (j = 0; j <= m; j++) {
          if (used[j]) { u[p[j]] += delta; v[j] -= delta; } else minv[j] -= delta;
        }
        j0 = j1;
      } while (p[j0] !== 0);
      do { var jw = way[j0]; p[j0] = p[jw]; j0 = jw; } while (j0);
    }
    var ans = [];
    for (j = 1; j <= m; j++) if (p[j]) ans[p[j] - 1] = j - 1;
    return ans;
  }

  function slotsFromSettings(settings) {
    var r = (settings && settings.roster) || {};
    var out = [];
    function add(slot, k) { for (var i = 0; i < (isWhole(k, 0, 20) ? k : 0); i++) out.push(slot); }
    add("QB", r.QB); add("RB", r.RB); add("WR", r.WR); add("TE", r.TE); add("FLEX", r.FLEX);
    if (settings && settings.superflex) add("SUPER_FLEX", settings.superflexSlots === 2 ? 2 : 1);
    add("K", r.K); add("DEF", r.DST); add("BN", r.BENCH);
    return out;
  }

  function rostersFromSleeper(rosters) {
    var out = {};
    (Array.isArray(rosters) ? rosters : []).forEach(function (r) {
      if (!r || r.roster_id === undefined || r.roster_id === null) return;
      var taxi = Array.isArray(r.taxi) ? r.taxi.map(String) : [];
      out[String(r.roster_id)] = (r.players || []).map(String).filter(function (id) { return taxi.indexOf(id) < 0; });
    });
    return out;
  }

  /* Weeks to project: fromWeek (default the first unscored week, record_through_week + 1) to the last playoff week
     (default start_week + rounds - 1, rounds = log2 of the bracket, one week per round), capped at week 18. */
  function weekWindow(state, opts) {
    opts = opts || {};
    var rules = (state && state.playoff_rules) || {};
    var from = isWhole(opts.fromWeek, 1, 22) ? opts.fromWeek : null, fromSrc = "opts.fromWeek";
    if (from === null) {
      var through = cellValue(state && state.record_through_week);
      if (isWhole(through, 0, 21)) { from = through + 1; fromSrc = "league-state record_through_week + 1"; }
    }
    var last = isWhole(opts.lastWeek, 1, 22) ? opts.lastWeek : null, lastSrc = "opts.lastWeek";
    if (last === null) {
      var start = cellValue(rules.start_week), spots = cellValue(rules.spots);
      if (isWhole(start, 2, 22) && isWhole(spots, 1, 32)) {
        var rounds = 0, size = 1; while (size < spots) { size *= 2; rounds++; }
        last = start + Math.max(rounds, 1) - 1;
        lastSrc = "derived: playoff start week " + start + " + " + Math.max(rounds, 1) + " one-week rounds for " + spots + " playoff teams";
      }
    }
    if (from === null) return {from: null, last: last, weeks: [], source: null, reason: "the first week to project is unknown (no fromWeek and no record_through_week)"};
    if (last === null) return {from: from, last: null, weeks: [], source: null, reason: "the last playoff week is unknown (no lastWeek and no playoff start week and spots)"};
    var capped = last > LAST_NFL_WEEK;
    var end = Math.min(last, LAST_NFL_WEEK), weeks = [];
    for (var w = from; w <= end; w++) weeks.push(w);
    var note = fromSrc + "; " + lastSrc + (capped ? "; capped at week " + LAST_NFL_WEEK + " (no NFL weeks after it)" : "");
    if (!weeks.length) return {from: from, last: last, weeks: [], source: note, reason: "no weeks left to project (from week " + from + " is after week " + end + ")"};
    return {from: from, last: last, weeks: weeks, source: note, reason: null};
  }

  /* one team, one week, one source: the player list the lineup chooses from, then the lineup */
  function teamWeek(ids, week, src, ctx) {
    var s = ctx.proj.bySource[src];
    if (!s || !s.weeks[week]) return {points: null, reason: "no " + label(src) + " projections for week " + week, lineup: [], unavailable: [], empty_slots: [], uncertain: []};
    var wkRows = s.byWeek[week] || {};
    var playing = ctx.sched && ctx.sched[week] ? ctx.sched[week] : null;
    var avail = [], unavailable = [], uncertain = {};
    ids.forEach(function (id) {
      var row = wkRows[id] || null;
      var info = ctx.players[id] || null;
      var pos = row && row.position ? String(row.position) : info && info[1] ? String(info[1]) : null;
      if (pos === "DEF" || pos === "K") return;   /* not projected in the warehouse; their slots are listed as not projected */
      var team = teamCode(row && row.team ? row.team : ctx.proj.teamOf[id] || (info ? info[2] : null));
      if (playing && team && !playing[team]) { unavailable.push({player_id: id, reason: "bye (" + team + " has no game in week " + week + ")"}); return; }
      var inj = injuryRule(ctx.inj[id], week);
      if (inj.out) { unavailable.push({player_id: id, reason: inj.out}); return; }
      if (!row) { unavailable.push({player_id: id, points: null, reason: "no " + label(src) + " projection for week " + week}); return; }
      var pts = num(ctx.points(row, {scoring: ctx.scoring, source: src, week: week}));
      if (pts === null) { unavailable.push({player_id: id, points: null, reason: label(src) + " row has no " + ctx.scoring + " points for week " + week}); return; }
      if (POSITIONS.indexOf(pos) < 0) { unavailable.push({player_id: id, reason: "position " + pos + " is not projected"}); return; }
      if (inj.uncertain) uncertain[id] = inj.uncertain;
      avail.push({id: id, pos: pos, points: pts});
    });
    var best = bestLineup(ctx.slots, avail);
    return {
      points: best.points, reason: null, lineup: best.lineup, unavailable: unavailable, empty_slots: best.empty_slots,
      uncertain: best.lineup.filter(function (l) { return l.player_id && uncertain[l.player_id]; })
        .map(function (l) { return {player_id: l.player_id, reason: uncertain[l.player_id]}; })
    };
  }

  function project(state, inputs, opts) {
    inputs = inputs || {}; opts = opts || {};
    var primary = opts.primary || "sleeper";
    var cross = opts.crossCheck === undefined ? "espn" : opts.crossCheck;
    var scoring = FORMAT_COLUMN[inputs.scoring] ? inputs.scoring : null;
    var slots = Array.isArray(inputs.slots) ? inputs.slots.map(String) : [];
    var win = weekWindow(state, opts);
    var proj = indexProjections(inputs.projections);
    var sources = {};
    [primary].concat(cross ? [cross] : []).forEach(function (src) {
      var s = proj.bySource[src];
      sources[src] = s ? {as_of: s.as_of, scoring_basis: s.basis, weeks: Object.keys(s.weeks).map(Number).sort(function (a, b) { return a - b; }), rows_without_player_id: s.unmatched}
        : {as_of: null, scoring_basis: null, weeks: [], rows_without_player_id: 0};
    });
    var out = {
      version: VERSION, ok: false, reason: null, league_id: state && state.league ? state.league.id : null,
      window: win,
      basis: {primary: primary, cross_check: cross, scoring: scoring, points: opts.points ? "opts.points" : "providerPoints (the source's stored points_" + (scoring || "?") + ")",
        slots: slots.filter(function (s) { return ELIGIBLE[s]; }),
        slots_not_projected: slots.filter(function (s) { return !ELIGIBLE[s] && NOT_STARTERS.indexOf(s) < 0; }),
        bye_source: Array.isArray(inputs.schedule) ? "nflverse schedule" : null},
      sources: sources, teams: []
    };
    if (!state || !Array.isArray(state.teams)) { out.reason = "league-state has no teams"; return out; }
    if (!scoring) { out.reason = "scoring format must be ppr, half_ppr or standard"; return out; }
    if (!out.basis.slots.length) { out.reason = "the league has no projected starter slots (QB, RB, WR, TE, FLEX, SUPER_FLEX)"; return out; }
    if (win.reason) { out.reason = win.reason; return out; }

    var ctx = {proj: proj, sched: indexSchedule(inputs.schedule), inj: indexInjuries(inputs.injuries), players: inputs.players || {},
      points: typeof opts.points === "function" ? opts.points : providerPoints, scoring: scoring, slots: slots};
    var rosters = inputs.rosters || {};
    out.teams = state.teams.map(function (t) {
      var ids = Array.isArray(rosters[t.id]) ? rosters[t.id].map(String) : null;
      var weeks = win.weeks.map(function (w) {
        if (!ids) return {week: w, points: null, reason: "no roster for this team", lineup: [], unavailable: [], flags: {}, cross_check: null};
        var a = teamWeek(ids, w, primary, ctx);
        var flags = {
          rest_starters_risk: w === LAST_NFL_WEEK,
          uncertain_return: a.uncertain,
          empty_slots: a.empty_slots,
          bye_unknown: !(ctx.sched && ctx.sched[w])
        };
        var cc = null;
        if (cross) {
          var b = teamWeek(ids, w, cross, ctx);
          cc = {source: cross, points: b.points, reason: b.reason, diff: a.points !== null && b.points !== null ? round2(a.points - b.points) : null, lineup: b.lineup, unavailable: b.unavailable};
        }
        return {week: w, points: a.points, reason: a.reason, lineup: a.lineup, unavailable: a.unavailable, flags: flags, cross_check: cc};
      });
      return {team_id: t.id, name: t.name, weeks: weeks};
    });
    out.ok = true;
    return out;
  }

  var api = {VERSION: VERSION, LAST_NFL_WEEK: LAST_NFL_WEEK, ELIGIBLE: ELIGIBLE, project: project, providerPoints: providerPoints,
    bestLineup: bestLineup, slotsFromSettings: slotsFromSettings, rostersFromSleeper: rostersFromSleeper, window: weekWindow};
  root.DDF = root.DDF || {};
  root.DDF.weeklyTeamProjection = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
