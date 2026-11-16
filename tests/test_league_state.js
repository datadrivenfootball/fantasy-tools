// test_league_state.js — JEG-1655: league-state contract validator (app/next/league-state.js). No network.
// Run: node tests/test_league_state.js
// 1. Sleeper, manual and partial fixtures validate. 2. Missing is null with a reason, never zero or silent.
// 3. Malformed shapes are rejected with a path and code.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const LS = require(path.join(__dirname, "..", "app", "next", "league-state.js"));
const FX = n => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "league-state", n + ".json"), "utf8"));
const codes = (s) => LS.validate(s).errors.map(e => e.path + ":" + e.code);
const hasErr = (s, p, c) => assert.ok(codes(s).includes(p + ":" + c), p + ":" + c + " not in " + JSON.stringify(codes(s)));

["sleeper", "manual", "partial"].forEach(n => {
  const r = LS.validate(FX(n));
  assert.deepStrictEqual(r.errors, [], n + " fixture should validate");
});
assert.strictEqual(LS.VERSION, "league-state/1");

// partial fixture: every missing cell is null with a reason, none is zero
const part = FX("partial");
part.teams.forEach(t => ["record", "points_for", "points_against"].forEach(k => {
  assert.strictEqual(t[k].value, null); assert.ok(t[k].reason);
}));

// missing without a reason, zero standing in for missing, and cell envelope problems
let s = FX("sleeper"); s.teams[0].points_for = LS.missing(""); hasErr(s, "teams[0].points_for.reason", "null_without_reason");
s = FX("sleeper"); s.teams[0].points_for = {value: 5}; hasErr(s, "teams[0].points_for.source", "cell");
s = FX("sleeper"); s.teams[0].points_for.source = null; hasErr(s, "teams[0].points_for.source", "no_source");
s = FX("sleeper"); s.teams[0].points_for.as_of = "not a date"; hasErr(s, "teams[0].points_for.as_of", "no_as_of");
s = FX("sleeper"); s.teams[0].points_for = "0"; hasErr(s, "teams[0].points_for", "cell");
s = FX("sleeper"); s.teams[0].record.value = {w: 7, l: 3}; hasErr(s, "teams[0].record.value", "value");
s = FX("sleeper"); s.teams[0].points_against.value = -1; hasErr(s, "teams[0].points_against.value", "value");
// identity and references
s = FX("sleeper"); s.teams[1].id = "1"; hasErr(s, "teams[1].id", "duplicate");
s = FX("sleeper"); s.my_team_id = "zz"; hasErr(s, "my_team_id", "reference");
s = FX("sleeper"); s.my_team_id = null; hasErr(s, "my_team_id", "null_without_reason");
s = FX("sleeper"); s.version = "league-state/2"; hasErr(s, "version", "version");
// schedule
s = FX("sleeper"); s.schedule.value[0].games[0].away = "9"; hasErr(s, "schedule.value", "value");
s = FX("sleeper"); s.schedule.value[0].games[1] = {home: "1", away: "2"}; hasErr(s, "schedule.value", "value");
s = FX("sleeper"); delete s.schedule.value[0].median_game; hasErr(s, "schedule.value", "value");
// playoff rules cross-checks
s = FX("sleeper"); s.playoff_rules.byes.value = 4; hasErr(s, "playoff_rules.byes", "cross");
s = FX("sleeper"); s.playoff_rules.last_regular_week.value = 13; hasErr(s, "playoff_rules.last_regular_week", "cross");
s = FX("sleeper"); s.playoff_rules.spots.value = 4; assert.deepStrictEqual(LS.validate(s).errors, []);
s = FX("sleeper"); s.playoff_rules.spots.value = 5; hasErr(s, "playoff_rules.spots.value", "value");
s = FX("sleeper"); s.playoff_rules.tiebreak.value = "coin"; hasErr(s, "playoff_rules.tiebreak.value", "value");
s = FX("sleeper"); s.trade_deadline_week.value = 0; hasErr(s, "trade_deadline_week.value", "value");
assert.strictEqual(LS.validate(null).ok, false);
assert.strictEqual(LS.validate([]).ok, false);
// helpers build valid cells
assert.deepStrictEqual(LS.missing("r"), {value: null, source: null, as_of: null, reason: "r"});

// review fixes (JEG-1655 round 1)
const bad = (mut, p, c) => { const x = FX("sleeper"); mut(x); hasErr(x, p, c); };
// strict dates
["1", "12", "Nov 16 2026", "2026-02-30T12:00:00Z", "2026-11-16", "2026-11-16T25:00:00Z"].forEach(d => {
  bad(x => { x.captured_at = d; }, "captured_at", "shape");
  bad(x => { x.teams[0].points_for.as_of = d; }, "teams[0].points_for.as_of", "no_as_of");
});
// known vs missing consistency, blank reasons
bad(x => { x.teams[0].points_for.reason = "because"; }, "teams[0].points_for.reason", "cell");
bad(x => { x.teams[0].division = {value: null, source: "x", as_of: null, reason: "r"}; }, "teams[0].division.source", "cell");
bad(x => { x.teams[0].division = {value: null, source: null, as_of: "2026-11-16T12:00:00Z", reason: "r"}; }, "teams[0].division.as_of", "cell");
bad(x => { x.teams[0].division = LS.missing("   "); }, "teams[0].division.reason", "null_without_reason");
bad(x => { x.my_team_id = null; x.my_team_missing_reason = "  "; }, "my_team_id", "null_without_reason");
// zero standing in for missing
bad(x => { x.teams[0].points_for = LS.missing(null); }, "teams[0].points_for.reason", "null_without_reason");
bad(x => { x.teams[0].points_for = {value: 0, source: null, as_of: null, reason: "not captured"}; }, "teams[0].points_for.source", "no_source");
// ids: strings only, prototype names are not teams
bad(x => { x.teams[0].id = 1; }, "teams[0].id", "shape");
bad(x => { x.my_team_id = "constructor"; }, "my_team_id", "reference");
bad(x => { x.my_team_id = 1; }, "my_team_id", "reference");
bad(x => { x.schedule.value[0].games[0].home = "constructor"; }, "schedule.value", "value");
bad(x => { x.schedule.value[0].games[0].home = 1; }, "schedule.value", "value");
// JEG-1656 nit: "constructor" (and other Object.prototype names) is a legal team id, found only when it is a real team
s = FX("sleeper");
const oldId = s.teams[0].id; s.teams[0].id = "constructor"; s.my_team_id = "constructor";
s.schedule.value.forEach(w => w.games.forEach(g => { if (g.home === oldId) g.home = "constructor"; if (g.away === oldId) g.away = "constructor"; }));
assert.deepStrictEqual(LS.validate(s).errors, [], "a team id of constructor validates when it is a team");
s.teams[0].id = "toString"; s.my_team_id = "toString"; s.schedule.value.forEach(w => w.games.forEach(g => { if (g.home === "constructor") g.home = "toString"; if (g.away === "constructor") g.away = "toString"; }));
assert.deepStrictEqual(LS.validate(s).errors, [], "toString too");
s = FX("sleeper"); s.teams[0].id = "constructor"; hasErr(s, "schedule.value", "value");   // schedule still names the old id: not a team
// JEG-1656 nit: the schedule week message names the enforced 1-21 range
s = FX("sleeper"); s.schedule.value[0].week = 22;
assert.ok(LS.validate(s).errors.some(e => e.path === "schedule.value" && /1-21/.test(e.message) && !/22/.test(e.message)), "week message says 1-21");
s = FX("sleeper"); s.schedule.value[0].week = 0; hasErr(s, "schedule.value", "value");
// schedule: duplicate week, team plays itself, window
bad(x => { x.schedule.value[1].week = 11; }, "schedule.value", "value");
bad(x => { x.schedule.value[0].games[0] = {home: "1", away: "1"}; }, "schedule.value", "value");
bad(x => { x.schedule.value[3].week = 15; }, "schedule.value[3].week", "cross");
bad(x => { x.schedule.value[0].week = 10; }, "schedule.value[0].week", "cross");
bad(x => { x.record_through_week.value = 15; }, "record_through_week", "cross");
bad(x => { x.record_through_week.value = -1; }, "record_through_week.value", "value");
// provider and capture
bad(x => { x.league.provider = "manual"; }, "league.provider", "value");
bad(x => { x.league.capture = "sleeper"; }, "league.capture", "value");
bad(x => { x.league.platform = "sleeper"; delete x.league.provider; }, "league.provider", "value");
// seeding rule vs divisions
bad(x => { x.playoff_rules.seeding_rule.value = "division_winners_first"; x.teams.forEach(t => { t.division = LS.missing("not entered"); }); }, "playoff_rules.seeding_rule", "cross");
s = FX("sleeper"); s.playoff_rules.seeding_rule.value = "division_winners_first"; assert.deepStrictEqual(LS.validate(s).errors, []);
// trade deadline: none is allowed, other strings are not
s = FX("sleeper"); s.trade_deadline_week.value = "none"; assert.deepStrictEqual(LS.validate(s).errors, []);
bad(x => { x.trade_deadline_week.value = "never"; }, "trade_deadline_week.value", "value");
// valid offset timestamp
s = FX("sleeper"); s.captured_at = "2026-11-16T07:00:00-05:00"; assert.deepStrictEqual(LS.validate(s).errors, []);
console.log("test_league_state: ok");
