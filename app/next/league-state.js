/* league-state contract validator (JEG-1655, part of JEG-1653). Contract: docs/contract/league-state-v1.md.
 * One versioned season-state shape that every capture path (Sleeper import, manual entry, paste, MCP state) writes
 * and every consumer reads. No value math and not wired into any page yet: this module only checks shape.
 *
 * Every field is a cell {value, source, as_of, reason}. A known value carries source and as_of; an unknown value is
 * null with a reason. Missing is never zero.
 *
 * DDF.leagueState.VERSION                   -> "league-state/1"
 * DDF.leagueState.known(value, source, asOf) -> cell
 * DDF.leagueState.missing(reason)           -> cell
 * DDF.leagueState.validate(state)           -> {ok, errors: [{path, code, message}]}
 *     codes: shape | version | cell | null_without_reason | no_source | no_as_of | value | reference | duplicate | cross
 */
(function (root) {
  "use strict";
  var VERSION = "league-state/1";
  var SEEDING = ["record", "division_winners_first"];
  var TIEBREAK = ["points_for", "head_to_head", "points_against", "other"];
  var PLATFORMS = ["sleeper", "espn", "yahoo", "manual", "mcp", "other"];

  function known(value, source, asOf) { return {value: value, source: source, as_of: asOf, reason: null}; }
  function missing(reason) { return {value: null, source: null, as_of: null, reason: reason}; }

  function isObj(x) { return x !== null && typeof x === "object" && !Array.isArray(x); }
  function isInt(x, lo, hi) { return typeof x === "number" && isFinite(x) && Math.floor(x) === x && x >= lo && x <= hi; }
  function isStr(x) { return typeof x === "string" && x.length > 0; }
  function isIso(x) { return isStr(x) && !isNaN(Date.parse(x)); }

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
        if (!isStr(c.reason)) err(path + ".reason", "null_without_reason", "a missing value needs a reason");
        return undefined;
      }
      if (!isStr(c.source)) err(path + ".source", "no_source", "a known value needs a source");
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
      if (PLATFORMS.indexOf(lg.platform) < 0) err("league.platform", "value", "platform must be one of " + PLATFORMS.join(", "));
      if (!isInt(lg.season, 2000, 2100)) err("league.season", "shape", "league.season must be a year");
    }
    if (!isIso(state.captured_at)) err("captured_at", "shape", "captured_at must be an ISO timestamp");

    var ids = {};
    var teams = state.teams;
    if (!Array.isArray(teams) || !teams.length) err("teams", "shape", "teams must be a non-empty array");
    else teams.forEach(function (t, i) {
      var p = "teams[" + i + "]";
      if (!isObj(t)) { err(p, "shape", "team must be an object"); return; }
      if (!isStr(t.id)) err(p + ".id", "shape", "stable team id must be a non-empty string");
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
      if (!ids[state.my_team_id]) err("my_team_id", "reference", "my_team_id is not a team id");
    } else if (!isStr(state.my_team_missing_reason)) err("my_team_id", "null_without_reason", "null my_team_id needs my_team_missing_reason");

    var weeks = cell("schedule", state.schedule, function (v) {
      if (!Array.isArray(v)) return "schedule value must be an array of weeks";
      var seen = {};
      for (var i = 0; i < v.length; i++) {
        var w = v[i];
        if (!isObj(w) || !isInt(w.week, 1, 22)) return "schedule[" + i + "].week must be 1-22";
        if (seen[w.week]) return "duplicate schedule week " + w.week;
        seen[w.week] = true;
        if (typeof w.median_game !== "boolean") return "schedule[" + i + "].median_game must be true or false";
        if (!Array.isArray(w.games)) return "schedule[" + i + "].games must be an array";
        var used = {};
        for (var j = 0; j < w.games.length; j++) {
          var g = w.games[j];
          if (!isObj(g) || !ids[g.home] || !ids[g.away]) return "schedule[" + i + "].games[" + j + "] needs home and away team ids";
          if (g.home === g.away) return "schedule[" + i + "].games[" + j + "] plays a team against itself";
          if (used[g.home] || used[g.away]) return "schedule[" + i + "] has a team in two games";
          used[g.home] = used[g.away] = true;
        }
      }
      return null;
    });
    void weeks;

    var pr = state.playoff_rules;
    var rules = {};
    if (!isObj(pr)) err("playoff_rules", "shape", "playoff_rules must be an object");
    else {
      rules.spots = cell("playoff_rules.spots", pr.spots, function (v) { return isInt(v, 1, teamCount || 99) ? null : "spots must be a whole number from 1 to the team count"; });
      rules.start = cell("playoff_rules.start_week", pr.start_week, function (v) { return isInt(v, 2, 22) ? null : "start_week must be 2-22"; });
      rules.last = cell("playoff_rules.last_regular_week", pr.last_regular_week, function (v) { return isInt(v, 1, 21) ? null : "last_regular_week must be 1-21"; });
      rules.byes = cell("playoff_rules.byes", pr.byes, function (v) { return isInt(v, 0, 99) ? null : "byes must be a whole number >= 0"; });
      cell("playoff_rules.seeding_rule", pr.seeding_rule, function (v) { return SEEDING.indexOf(v) >= 0 ? null : "seeding_rule must be one of " + SEEDING.join(", "); });
      cell("playoff_rules.tiebreak", pr.tiebreak, function (v) { return TIEBREAK.indexOf(v) >= 0 ? null : "tiebreak must be one of " + TIEBREAK.join(", "); });
      cell("playoff_rules.division_winners_seeded", pr.division_winners_seeded, function (v) { return typeof v === "boolean" ? null : "must be true or false"; });
      if (rules.spots !== undefined && rules.byes !== undefined && rules.byes > rules.spots) err("playoff_rules.byes", "cross", "byes cannot exceed spots");
      if (rules.start !== undefined && rules.last !== undefined && rules.last !== rules.start - 1) err("playoff_rules.last_regular_week", "cross", "last_regular_week must equal start_week - 1");
    }
    cell("trade_deadline_week", state.trade_deadline_week, function (v) { return isInt(v, 1, 22) ? null : "trade_deadline_week must be 1-22"; });

    return {ok: errors.length === 0, errors: errors};
  }

  var api = {VERSION: VERSION, known: known, missing: missing, validate: validate};
  root.DDF = root.DDF || {};
  root.DDF.leagueState = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
