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
console.log("test_league_state: ok");
