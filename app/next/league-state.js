/* league-state contract validator (JEG-1655, part of JEG-1653). Contract: docs/contract/league-state-v1.md.
 * One versioned season-state shape that every capture path (Sleeper import, manual entry, paste, MCP state) writes
 * and every consumer reads. No value math and not wired into any page yet: this module only checks shape.
 *
 * league.provider is where the league lives (sleeper, espn, yahoo, other); league.capture is how the data got here
 * (import, manual, paste, mcp).
 * Every field is a cell {value, source, as_of, reason}. A known value carries source and as_of; an unknown value is
 * null with a reason. Missing is never zero.
 *
 * DDF.leagueState.VERSION                   -> "league-state/1"
 * DDF.leagueState.known(value, source, asOf) -> cell
 * DDF.leagueState.missing(reason)           -> cell
 * DDF.leagueState.validate(state)           -> {ok, errors: [{path, code, message}]}
 * DDF.leagueState.weekPlan(state)           -> {regularEnd, playoffLo, source, as_of} | {why}   (JEG-1685: the ES-12 week settings the state knows)
 * DDF.leagueState.weekFill(state, cur, def, prior) -> {patch, plan, why}   cur/def/prior = {regularEnd, playoffLo, playoffHi} | null
 *     patch is the engine weeks to apply, or null with why. A value the reader changed (cur differs from the site default
 *     and from what a state filled before, prior) is never replaced.
 *     codes: shape | version | cell | null_without_reason | no_source | no_as_of | value | reference | duplicate | cross
 */
(function (root) {
  "use strict";
  var VERSION = "league-state/1";
  var SEEDING = ["record", "division_winners_first"];
  var TIEBREAK = ["points_for", "head_to_head", "points_against", "other"];
  var PROVIDERS = ["sleeper", "espn", "yahoo", "other"];
  var CAPTURES = ["import", "manual", "paste", "mcp"];
  var ISO = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/;

  function known(value, source, asOf) { return {value: value, source: source, as_of: asOf, reason: null}; }
  function missing(reason) { return {value: null, source: null, as_of: null, reason: reason}; }

  function isObj(x) { return x !== null && typeof x === "object" && !Array.isArray(x); }
  function isInt(x, lo, hi) { return typeof x === "number" && isFinite(x) && Math.floor(x) === x && x >= lo && x <= hi; }
  function isStr(x) { return typeof x === "string" && x.length > 0; }
  function isIso(x) {
    var m = typeof x === "string" ? ISO.exec(x) : null;
    if (!m) return false;
    var y = +m[1], mo = +m[2], d = +m[3], dt = new Date(Date.UTC(y, mo - 1, d));
    return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d && +m[4] <= 23 && +m[5] <= 59 && (m[6] === undefined || +m[6] <= 59);
  }
  function isText(x) { return typeof x === "string" && x.trim().length > 0; }

  function validate(state) {
    var errors = [];
    function err(path, code, message) { errors.push({path: path, code: code, message: message}); }

    // Check a cell's envelope, then its value with check(value) -> message or null. Returns the value, or undefined when unusable.
    function cell(path, c, check) {
      if (!isObj(c)) { err(path, "cell", "must be a cell {value, source, as_of, reason}"); return undefined; }
      var ok = true;
      ["value", "source", "as_of", "reason"].forEach(function (k) { if (!(k in c)) { err(path + "." + k, "cell", "cell key is missing"); ok = false; } });
      if (!ok) return undefined;
      if (c.value === null) {
        if (!isText(c.reason)) err(path + ".reason", "null_without_reason", "a missing value needs a non-blank reason");
        if (c.source !== null) err(path + ".source", "cell", "a missing value must have source null");
        if (c.as_of !== null) err(path + ".as_of", "cell", "a missing value must have as_of null");
        return undefined;
      }
      if (c.reason !== null) err(path + ".reason", "cell", "a known value must have reason null");
      if (!isText(c.source)) err(path + ".source", "no_source", "a known value needs a source");
      if (!isIso(c.as_of)) err(path + ".as_of", "no_as_of", "a known value needs an ISO as_of timestamp");
      var msg = check(c.value);
      if (msg) { err(path + ".value", "value", msg); return undefined; }
      return c.value;
    }

    if (!isObj(state)) return {ok: false, errors: [{path: "", code: "shape", message: "league-state must be an object"}]};
    if (state.version !== VERSION) err("version", "version", "version must be " + JSON.stringify(VERSION));

    var lg = state.league;
    if (!isObj(lg)) err("league", "shape", "league must be an object");
    else {
      if (!isStr(lg.id)) err("league.id", "shape", "league.id must be a non-empty string");
      if (PROVIDERS.indexOf(lg.provider) < 0) err("league.provider", "value", "provider must be one of " + PROVIDERS.join(", "));
      if (CAPTURES.indexOf(lg.capture) < 0) err("league.capture", "value", "capture must be one of " + CAPTURES.join(", "));
      if (!isInt(lg.season, 2000, 2100)) err("league.season", "shape", "league.season must be a year");
    }
    if (!isIso(state.captured_at)) err("captured_at", "shape", "captured_at must be an ISO timestamp");

    var ids = Object.create(null);
    var teams = state.teams;
    if (!Array.isArray(teams) || !teams.length) err("teams", "shape", "teams must be a non-empty array");
    else teams.forEach(function (t, i) {
      var p = "teams[" + i + "]";
      if (!isObj(t)) { err(p, "shape", "team must be an object"); return; }
      if (!isText(t.id)) err(p + ".id", "shape", "stable team id must be a non-empty string");
      else if (ids[t.id]) err(p + ".id", "duplicate", "duplicate team id " + t.id);
      else ids[t.id] = true;
      if (!isStr(t.name)) err(p + ".name", "shape", "team name must be a non-empty string");
      cell(p + ".record", t.record, function (v) {
        return isObj(v) && isInt(v.w, 0, 99) && isInt(v.l, 0, 99) && isInt(v.t, 0, 99) ? null : "record must be {w, l, t} whole numbers";
      });
      ["points_for", "points_against"].forEach(function (k) {
        cell(p + "." + k, t[k], function (v) { return typeof v === "number" && isFinite(v) && v >= 0 ? null : k + " must be a number >= 0"; });
      });
      cell(p + ".division", t.division, function (v) { return isStr(v) ? null : "division must be a non-empty string"; });
    });
    var teamCount = Array.isArray(teams) ? teams.length : 0;

    if (state.my_team_id !== null && state.my_team_id !== undefined) {
      if (typeof state.my_team_id !== "string" || ids[state.my_team_id] !== true) err("my_team_id", "reference", "my_team_id is not a team id");
    } else if (!isText(state.my_team_missing_reason)) err("my_team_id", "null_without_reason", "null my_team_id needs my_team_missing_reason");

    var through = cell("record_through_week", state.record_through_week, function (v) { return isInt(v, 0, 21) ? null : "record_through_week must be a whole number 0-21 (0 = no games played)"; });
    var sched = cell("schedule", state.schedule, function (v) {
      if (!Array.isArray(v)) return "schedule value must be an array of weeks";
      var seen = Object.create(null);
      for (var i = 0; i < v.length; i++) {
        var w = v[i];
        if (!isObj(w) || !isInt(w.week, 1, 21)) return "schedule[" + i + "].week must be a whole number 1-21";
        if (seen[w.week]) return "duplicate schedule week " + w.week;
        seen[w.week] = true;
        if (typeof w.median_game !== "boolean") return "schedule[" + i + "].median_game must be true or false";
        if (!Array.isArray(w.games)) return "schedule[" + i + "].games must be an array";
        var used = Object.create(null);
        for (var j = 0; j < w.games.length; j++) {
          var g = w.games[j];
          if (!isObj(g) || typeof g.home !== "string" || typeof g.away !== "string" || ids[g.home] !== true || ids[g.away] !== true) return "schedule[" + i + "].games[" + j + "] needs home and away team ids";
          if (g.home === g.away) return "schedule[" + i + "].games[" + j + "] plays a team against itself";
          if (used[g.home] || used[g.away]) return "schedule[" + i + "] has a team in two games";
          used[g.home] = used[g.away] = true;
        }
      }
      return null;
    });
    var pr = state.playoff_rules;
    var rules = {};
    if (!isObj(pr)) err("playoff_rules", "shape", "playoff_rules must be an object");
    else {
      rules.spots = cell("playoff_rules.spots", pr.spots, function (v) { return isInt(v, 1, teamCount || 99) ? null : "spots must be a whole number from 1 to the team count"; });
      rules.start = cell("playoff_rules.start_week", pr.start_week, function (v) { return isInt(v, 2, 22) ? null : "start_week must be 2-22"; });
      rules.last = cell("playoff_rules.last_regular_week", pr.last_regular_week, function (v) { return isInt(v, 1, 21) ? null : "last_regular_week must be 1-21"; });
      rules.byes = cell("playoff_rules.byes", pr.byes, function (v) { return isInt(v, 0, 99) ? null : "byes must be a whole number >= 0"; });
      rules.seeding = cell("playoff_rules.seeding_rule", pr.seeding_rule, function (v) { return SEEDING.indexOf(v) >= 0 ? null : "seeding_rule must be one of " + SEEDING.join(", "); });
      cell("playoff_rules.tiebreak", pr.tiebreak, function (v) { return TIEBREAK.indexOf(v) >= 0 ? null : "tiebreak must be one of " + TIEBREAK.join(", "); });
      if (rules.seeding === "division_winners_first" && Array.isArray(teams) && teams.length && teams.every(function (t) { return isObj(t) && isObj(t.division) && t.division.value === null; })) {
        err("playoff_rules.seeding_rule", "cross", "division_winners_first needs at least one team division");
      }
      if (rules.spots !== undefined && rules.byes !== undefined && rules.byes > rules.spots) err("playoff_rules.byes", "cross", "byes cannot exceed spots");
      if (rules.start !== undefined && rules.last !== undefined && rules.last !== rules.start - 1) err("playoff_rules.last_regular_week", "cross", "last_regular_week must equal start_week - 1");
    }
    cell("trade_deadline_week", state.trade_deadline_week, function (v) { return v === "none" || isInt(v, 1, 22) ? null : 'trade_deadline_week must be 1-22 or "none" (no deadline)'; });
    if (through !== undefined && rules.last !== undefined && through > rules.last) err("record_through_week", "cross", "record_through_week cannot exceed last_regular_week");
    if (Array.isArray(sched)) sched.forEach(function (w, i) {
      if (!isObj(w)) return;
      if (rules.last !== undefined && w.week > rules.last) err("schedule.value[" + i + "].week", "cross", "schedule week " + w.week + " is after last_regular_week");
      if (through !== undefined && w.week <= through) err("schedule.value[" + i + "].week", "cross", "schedule week " + w.week + " is not after record_through_week");
    });

    return {ok: errors.length === 0, errors: errors};
  }

  // JEG-1685: the ES-12 week settings (playoffs start week, last regular-season week) a state knows. Needs a valid state and a
  // known start_week or last_regular_week; the other is derived (last = start - 1). source and as_of come from the cell used.
  function weekPlan(state) {
    if (!validate(state).ok) return {why: "The league state is not valid, so its weeks are not used."};
    var pr = state.playoff_rules, s = pr.start_week, l = pr.last_regular_week, c;
    if (s.value !== null) c = s; else if (l.value !== null) c = l;
    else return {why: s.reason || l.reason};
    var lo = s.value !== null ? s.value : l.value + 1;
    return {regularEnd: lo - 1, playoffLo: lo, source: c.source, as_of: c.as_of};
  }
  function sameWeeks(a, b) { return !!a && !!b && a.regularEnd === b.regularEnd && a.playoffLo === b.playoffLo && a.playoffHi === b.playoffHi; }
  function weekFill(state, cur, def, prior) {
    var plan = weekPlan(state);
    if (plan.why) return {patch: null, plan: null, why: plan.why};
    if (!cur) return {patch: null, plan: plan, why: "The engine's current weeks are not available."};
    if (!sameWeeks(cur, def) && !sameWeeks(cur, prior)) return {patch: null, plan: plan, why: "The weeks were set by the reader; they stay."};
    if (plan.playoffLo > 18 || plan.regularEnd < 1) return {patch: null, plan: plan, why: "The league's weeks are outside the engine's 1 to 18."};
    if (plan.playoffLo > cur.playoffHi) return {patch: null, plan: plan, why: "The league's playoffs start after the engine's last playoff week; the league does not say when they end."};
    return {patch: {regularEnd: plan.regularEnd, playoffLo: plan.playoffLo, playoffHi: cur.playoffHi}, plan: plan, why: null};
  }

  var api = {VERSION: VERSION, known: known, missing: missing, validate: validate, weekPlan: weekPlan, weekFill: weekFill};
  root.DDF = root.DDF || {};
  root.DDF.leagueState = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
