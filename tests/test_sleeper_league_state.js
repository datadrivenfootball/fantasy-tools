// test_sleeper_league_state.js — JEG-1656: Sleeper import builds a league-state/1 object (app/next/sleeper-import.js).
// Fixtures in tests/fixtures/sleeper-live/ are recorded live public Sleeper API responses (2026-11-16): a full in-season
// league, a league with divisions, no trade deadline (99) and a median game, and a pre-draft league. No live calls here.
// Run: node tests/test_sleeper_league_state.js
// 1. Each recorded league validates under DDF.leagueState.validate and carries the values Sleeper returned.
// 2. Missing is null with a reason, never zero: no matchups, empty preseason weeks, absent fields, a failed fetch.
// 3. trade_deadline 99 is "none"; playoff_seed_type does not drive seeding_rule (divisions do); byes from playoff_teams.
// 4. load(id, {leagueState:true}) adds the leagueState and the per-week matchups calls; without it nothing changes.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const sys = require("child_process");
const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
globalThis.DDFRosterPaste = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
require(path.join(ROOT, "app", "next", "rosterparse.js"));
require(path.join(ROOT, "app", "next", "league-paste.js"));
const LS = require(path.join(ROOT, "app", "next", "league-state.js"));
const SL = require(path.join(ROOT, "app", "next", "sleeper-import.js"));
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const ROWS = TABLE.map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });
const live = n => JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "sleeper-live", n + ".json"), "utf8"));
const NOW = "2026-11-16T18:00:00Z";
const build = (fx, mut) => {
  const d = JSON.parse(JSON.stringify(fx));
  if (mut) mut(d);
  const m = {}; Object.keys(d.matchups).forEach(k => { m[k] = d.matchups[k]; });
  return SL.buildLeagueState(d.league, d.users, d.rosters, m, {now: NOW});
};
const valid = st => assert.deepStrictEqual(LS.validate(st).errors, [], "should validate");
const noZeroForMissing = st => {
  const cells = [st.record_through_week, st.schedule, st.trade_deadline_week].concat(Object.values(st.playoff_rules));
  st.teams.forEach(t => cells.push(t.record, t.points_for, t.points_against, t.division));
  cells.forEach(c => { if (c.value === null) { assert.ok(c.reason && c.source === null && c.as_of === null); } else { assert.ok(c.source && c.as_of && c.reason === null); } });
};

let passed = 0, failed = 0;
const queue = [];
function test(name, fn) { queue.push([name, fn]); }

test("full league: records, PF/PA, playoff rules, deadline, remaining schedule", () => {
  const st = build(live("full"));
  valid(st); noZeroForMissing(st);
  assert.strictEqual(st.league.provider, "sleeper"); assert.strictEqual(st.league.capture, "import"); assert.strictEqual(st.league.season, 2026);
  assert.strictEqual(st.captured_at, NOW);
  assert.strictEqual(st.teams.length, 12);
  const t1 = st.teams[0];
  assert.strictEqual(t1.id, "1");
  assert.deepStrictEqual(t1.record.value, {w: 6, l: 3, t: 0});
  assert.strictEqual(t1.points_for.value, 1283.22);        // fpts 1283 + fpts_decimal 22
  assert.strictEqual(t1.points_against.value, 1005.42);    // fpts_against 1005 + fpts_against_decimal 42
  assert.strictEqual(t1.record.source, "sleeper:rosters.settings.wins+losses+ties");
  assert.strictEqual(t1.record.as_of, NOW);
  assert.strictEqual(t1.division.value, null); assert.ok(/no divisions/.test(t1.division.reason));
  assert.strictEqual(st.record_through_week.value, 9);      // last_scored_leg; wins+losses+ties = 9 games
  assert.strictEqual(st.playoff_rules.spots.value, 6);
  assert.strictEqual(st.playoff_rules.start_week.value, 15);
  assert.strictEqual(st.playoff_rules.last_regular_week.value, 14);
  assert.strictEqual(st.playoff_rules.byes.value, 2);
  assert.strictEqual(st.playoff_rules.seeding_rule.value, "record");
  assert.strictEqual(st.playoff_rules.tiebreak.value, null); assert.ok(st.playoff_rules.tiebreak.reason);
  assert.strictEqual(st.trade_deadline_week.value, 14);
  assert.strictEqual(st.my_team_id, null); assert.ok(st.my_team_missing_reason);
  const sch = st.schedule.value;
  assert.deepStrictEqual(sch.map(w => w.week), [10, 11, 12, 13, 14]);   // week 10 is in progress and still remaining; 15 is a playoff week
  sch.forEach(w => { assert.strictEqual(w.games.length, 6); assert.strictEqual(w.median_game, false); });
  assert.deepStrictEqual(SL.remainingWeeks(live("full").league, live("full").rosters), [10, 11, 12, 13, 14]);
});

test("divisions league: 99 is no deadline, median game, division names, division winners first", () => {
  const fx = live("divisions");
  assert.strictEqual(fx.league.settings.playoff_seed_type, 0);   // recorded as returned: seed type 0 with divisions
  const st = build(fx);
  valid(st); noZeroForMissing(st);
  assert.strictEqual(fx.league.settings.trade_deadline, 99);
  assert.strictEqual(st.trade_deadline_week.value, "none");
  assert.ok(/99/.test(st.trade_deadline_week.source));
  assert.strictEqual(st.playoff_rules.seeding_rule.value, "division_winners_first");
  assert.deepStrictEqual(Array.from(new Set(st.teams.map(t => t.division.value))).sort(), ["North", "South"]);
  assert.ok(st.schedule.value.length && st.schedule.value.every(w => w.median_game === true && w.games.length === 5));
  // playoff_seed_type 1 gives the same rule: it is not the switch
  const st1 = build(fx, d => { d.league.settings.playoff_seed_type = 1; });
  assert.strictEqual(st1.playoff_rules.seeding_rule.value, "division_winners_first");
  // no divisions: record, whatever the seed type
  const st2 = build(live("full"), d => { d.league.settings.playoff_seed_type = 1; });
  assert.strictEqual(st2.playoff_rules.seeding_rule.value, "record");
});

test("trade_deadline: 99 is none, weeks pass through, anything else is missing with a reason", () => {
  const dl = v => build(live("full"), d => { if (v === undefined) delete d.league.settings.trade_deadline; else d.league.settings.trade_deadline = v; }).trade_deadline_week;
  assert.strictEqual(dl(99).value, "none");
  assert.strictEqual(dl(11).value, 11);
  [0, 23, "14", null, undefined].forEach(v => { const c = dl(v); assert.strictEqual(c.value, null, String(v)); assert.ok(c.reason); });
});

test("byes from playoff_teams: verified sizes only", () => {
  const byes = n => build(live("full"), d => { d.league.settings.playoff_teams = n; }).playoff_rules.byes;
  [[4, 0], [5, 3], [6, 2], [7, 1], [8, 0]].forEach(([n, b]) => assert.strictEqual(byes(n).value, b, n + " teams"));
  [2, 3, 10, 12].forEach(n => { const c = byes(n); assert.strictEqual(c.value, null); assert.ok(/not verified/.test(c.reason)); });
  const over = build(live("full"), d => { d.league.settings.playoff_teams = 13; }).playoff_rules.spots;   // more spots than teams
  assert.strictEqual(over.value, null);
});

test("preseason (pre-draft): 0-0-0 is a real record, unknown pieces are null with a reason, schedule not generated", () => {
  const fx = live("preseason");
  assert.strictEqual(fx.league.status, "pre_draft");
  assert.ok(!("last_scored_leg" in fx.league.settings));
  const st = build(fx);
  valid(st); noZeroForMissing(st);
  assert.deepStrictEqual(st.teams[0].record.value, {w: 0, l: 0, t: 0});
  assert.strictEqual(st.record_through_week.value, 0);
  assert.ok(/preseason/.test(st.record_through_week.source));
  assert.strictEqual(st.teams[0].points_against.value, null);   // fpts_against is not returned before games are scored
  assert.ok(/fpts_against/.test(st.teams[0].points_against.reason));
  assert.strictEqual(st.schedule.value, null);
  assert.ok(/week 1: Sleeper has not generated matchups/.test(st.schedule.reason));
  assert.strictEqual(st.playoff_rules.start_week.value, 15);
});

test("partial: absent pieces become missing cells with a reason, never zero", () => {
  const st = build(live("full"), d => {
    delete d.league.settings.playoff_week_start; delete d.league.settings.playoff_teams; delete d.league.settings.trade_deadline;
    delete d.league.settings.last_scored_leg; delete d.league.settings.divisions;
    delete d.rosters[0].settings.wins; delete d.rosters[1].settings.fpts; delete d.rosters[2].settings.fpts_against;
  });
  valid(st); noZeroForMissing(st);
  assert.strictEqual(st.teams[0].record.value, null);
  assert.strictEqual(st.teams[1].points_for.value, null);
  assert.strictEqual(st.teams[2].points_against.value, null);
  assert.strictEqual(st.record_through_week.value, null);
  assert.strictEqual(st.schedule.value, null);
  ["spots", "start_week", "last_regular_week", "byes"].forEach(k => assert.strictEqual(st.playoff_rules[k].value, null, k));
  assert.strictEqual(st.playoff_rules.seeding_rule.value, "record");   // divisions absent = no divisions
  assert.strictEqual(st.trade_deadline_week.value, null);
  assert.ok(st.teams[3].record.value && st.teams[3].points_for.value > 0);   // the rest of the league is still read
});

test("schedule is null with a reason when any week is unavailable or malformed", () => {
  const miss = (fn) => build(live("full"), fn).schedule;
  let c = miss(d => { delete d.matchups["12"]; });
  assert.strictEqual(c.value, null); assert.ok(/week 12/.test(c.reason));
  c = miss(d => { d.matchups["13"] = null; });
  assert.strictEqual(c.value, null); assert.ok(/week 13: Sleeper returned no matchups/.test(c.reason));
  c = miss(d => { d.matchups["11"] = []; });
  assert.ok(/week 11: Sleeper has not generated/.test(c.reason));
  c = miss(d => { d.matchups["10"][0].matchup_id = null; });
  assert.ok(/week 10: a team has no matchup_id/.test(c.reason));
  c = miss(d => { d.matchups["10"][0].matchup_id = 99; });
  assert.ok(/does not pair two teams/.test(c.reason));
  c = miss(d => { d.matchups["10"][0].roster_id = 77; });
  assert.ok(/unknown roster/.test(c.reason));
});

test("after the regular season: records cap at last_regular_week and nothing remains (a known empty schedule)", () => {
  const st = build(live("full"), d => { d.league.settings.last_scored_leg = 16; });
  valid(st);
  assert.strictEqual(st.record_through_week.value, 14);
  assert.ok(/capped/.test(st.record_through_week.source));
  assert.deepStrictEqual(st.schedule.value, []);
});

test("my team id is kept only when it is a team", () => {
  const fx = live("full");
  const st = SL.buildLeagueState(fx.league, fx.users, fx.rosters, fx.matchups, {now: NOW, myTeamId: 3});
  assert.strictEqual(st.my_team_id, "3"); valid(st);
  const bad = SL.buildLeagueState(fx.league, fx.users, fx.rosters, fx.matchups, {now: NOW, myTeamId: 99});
  assert.strictEqual(bad.my_team_id, null); assert.ok(bad.my_team_missing_reason); valid(bad);
});

/* ---- load() integration ---- */
const PLAYERS = JSON.parse(sys.execFileSync("python3", ["-c",
  "import sys,json; sys.path.insert(0,'pipelines'); import build_root_pages as b; print(json.dumps(b.sleeper_players()))"], {cwd: ROOT}).toString());
function fakeFetch(map, calls) {
  return url => {
    if (calls) calls.push(url);
    const hit = Object.keys(map).find(k => url.endsWith(k));
    if (hit === undefined) return Promise.resolve({ok: false, status: 404, json: () => Promise.resolve(null)});
    const v = map[hit];
    if (v instanceof Error) return Promise.reject(v);
    return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(v)});
  };
}
function routes(fx, over) {
  const id = fx.league.league_id, m = {
    [`/league/${id}`]: fx.league, [`/league/${id}/users`]: fx.users, [`/league/${id}/rosters`]: fx.rosters,
    "/state/nfl": fx.state, "sleeper-players.json": PLAYERS};
  Object.keys(fx.matchups).forEach(w => { if (fx.matchups[w]) m[`/league/${id}/matchups/${w}`] = fx.matchups[w]; });
  return Object.assign(m, over || {});
}
// the recorded rosters keep 3 players each; make them real ones so the paste path accepts the league
function playable(fx) {
  const d = JSON.parse(JSON.stringify(fx)), ids = Object.keys(PLAYERS.p).slice(0, 40);
  d.rosters.forEach((r, i) => { r.players = ids.slice(i * 3, i * 3 + 3); });
  return d;
}

test("load with leagueState: validates, fetches one matchups call per remaining week, Sleeper only", async () => {
  const fx = playable(live("full")), calls = [];
  const out = await SL.load(fx.league.league_id, {fetch: fakeFetch(routes(fx), calls), rows: ROWS, table: TABLE, leagueState: true, now: NOW});
  assert.strictEqual(out.ok, true);
  valid(out.leagueState);
  assert.strictEqual(out.leagueState.league.id, fx.league.league_id);
  const sleeper = calls.filter(u => u.startsWith("https://api.sleeper.app/v1/"));
  assert.strictEqual(sleeper.length, 4 + 5, "4 base calls + weeks 10-14");
  assert.deepStrictEqual(sleeper.filter(u => /matchups/.test(u)).map(u => Number(u.split("/").pop())).sort((a, b) => a - b), [10, 11, 12, 13, 14]);
  assert.ok(calls.every(u => u.startsWith("https://api.sleeper.app/v1/") || u === "sleeper-players.json"));
});

test("load without leagueState is unchanged: 4 calls, no leagueState", async () => {
  const fx = playable(live("full")), calls = [];
  const out = await SL.load(fx.league.league_id, {fetch: fakeFetch(routes(fx), calls), rows: ROWS, table: TABLE});
  assert.strictEqual(out.ok, true);
  assert.ok(!("leagueState" in out));
  assert.strictEqual(calls.filter(u => u.startsWith("https://api.sleeper.app/v1/")).length, 4);
});

test("load with leagueState: a failed matchups call nulls the schedule and never fails the import", async () => {
  const fx = playable(live("full"));
  const id = fx.league.league_id;
  const out = await SL.load(id, {fetch: fakeFetch(routes(fx, {[`/league/${id}/matchups/12`]: new Error("offline")}), []), rows: ROWS, table: TABLE, leagueState: true, now: NOW});
  assert.strictEqual(out.ok, true);
  valid(out.leagueState);
  assert.strictEqual(out.leagueState.schedule.value, null);
  assert.ok(/week 12/.test(out.leagueState.schedule.reason));
  assert.strictEqual(out.leagueState.teams[0].record.value.w, 6);
});

test("load of a pre-draft league with leagueState: one matchups call (empty), then the schedule is null with a reason", async () => {
  const fx = playable(live("preseason")), calls = [];
  const out = await SL.load(fx.league.league_id, {fetch: fakeFetch(routes(fx), calls), rows: ROWS, table: TABLE, leagueState: true, now: NOW});
  assert.strictEqual(out.ok, true);
  valid(out.leagueState);
  assert.deepStrictEqual(calls.filter(u => /matchups/.test(u)).map(u => Number(u.split("/").pop())), [1]);
  assert.strictEqual(out.leagueState.schedule.value, null);
  assert.deepStrictEqual(out.leagueState.teams[0].record.value, {w: 0, l: 0, t: 0});
});

(async function run() {
  for (const [name, fn] of queue) {
    try { await fn(); passed++; } catch (e) { failed++; console.error("FAIL " + name + "\n  " + (e && e.message)); }
  }
  console.log("test_sleeper_league_state: " + passed + " passed, " + failed + " failed");
  if (failed) process.exit(1);
})();
