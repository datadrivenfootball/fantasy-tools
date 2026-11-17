// test_weekly_team_projection.js — JEG-1658: best-lineup expected points per team per week (app/next/weekly-team-projection.js).
// Fixtures: tests/fixtures/weekly-team-projection/small.json (fake league, ids and teams; warehouse-shaped rows) and
// tests/fixtures/sleeper-live/full.json (the Sleeper producer's recorded superflex league; players swapped for fake ids).
// Run: node tests/test_weekly_team_projection.js
// 1. Bye (nflverse schedule, LA/LAR alias), out player, returning player (zero before his week, counted and flagged after),
//    a player's missing week (null with a reason, next player fills in), a whole missing week (null for every team).
// 2. Superflex and overlapping flex slots: the lineup is the exact optimum (brute force agrees; greedy would not).
// 3. ESPN cross-check is computed alongside, never blended; week 18 carries the rest-starters flag.
// 4. The points function is one injectable function (JEG-1688 swap point); the module is pure.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
const LS = require(path.join(ROOT, "app", "next", "league-state.js"));
const SL = require(path.join(ROOT, "app", "next", "sleeper-import.js"));
const WTP = require(path.join(ROOT, "app", "next", "weekly-team-projection.js"));
const fx = n => JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", n), "utf8"));
const SMALL = fx("weekly-team-projection/small.json");
const clone = x => JSON.parse(JSON.stringify(x));
const inputsOf = d => ({rosters: d.rosters, slots: d.slots, scoring: d.scoring, projections: d.projections, schedule: d.schedule, injuries: d.injuries, players: d.players});
const run = (mut, opts) => { const d = clone(SMALL); if (mut) mut(d); return WTP.project(d.state, inputsOf(d), opts); };
const wk = (res, teamId, w) => res.teams.find(t => t.team_id === teamId).weeks.find(x => x.week === w);
const starters = week => week.lineup.filter(l => l.player_id).map(l => l.slot + ":" + l.player_id).sort();
const reasonOf = (week, id) => (week.unavailable.find(u => u.player_id === id) || {}).reason;

let passed = 0, failed = 0;
const queue = [];
function test(name, fn) { queue.push([name, fn]); }

test("fixture league-state is valid", () => {
  assert.deepStrictEqual(LS.validate(SMALL.state).errors, []);
});

test("window: first unscored week to the last playoff week; a week with no rows is null for every team", () => {
  const r = run();
  assert.strictEqual(r.ok, true, r.reason);
  assert.deepStrictEqual(r.window.weeks, [12, 13, 14, 15]);   // through 11 + 1; start 15, 2 spots = one round
  r.teams.forEach(t => {
    const w15 = t.weeks.find(x => x.week === 15);
    assert.strictEqual(w15.points, null);
    assert.ok(/no Sleeper projections for week 15/.test(w15.reason));
    assert.strictEqual(w15.cross_check.points, null);
  });
});

test("bye, out-until-return and missing week: team 1", () => {
  const r = run();
  const w12 = wk(r, "1", 12), w13 = wk(r, "1", 13), w14 = wk(r, "1", 14);
  // week 12: DDD on bye (ra3, ta1), ta2 on IR until week 13, so the TE slot is empty; qa2 fills SUPER_FLEX
  assert.strictEqual(w12.points, 96);
  assert.deepStrictEqual(w12.flags.empty_slots, ["TE"]);
  assert.ok(/^bye \(DDD/.test(reasonOf(w12, "fk-ra3")));
  assert.ok(/^bye \(DDD/.test(reasonOf(w12, "fk-ta1")));
  assert.ok(/IR, expected back week 13/.test(reasonOf(w12, "fk-ta2")));
  assert.ok(starters(w12).includes("SUPER_FLEX:fk-qa2"));
  // week 13: LAR (nflverse LA) on bye; ta2 back and flagged uncertain; ra3 takes FLEX
  assert.strictEqual(w13.points, 99);
  assert.ok(/^bye \(LA /.test(reasonOf(w13, "fk-wa1")));
  assert.deepStrictEqual(w13.flags.uncertain_return.map(u => u.player_id), ["fk-ta2"]);
  assert.ok(starters(w13).includes("TE:fk-ta2") && starters(w13).includes("FLEX:fk-ra3"));
  // week 14: wa3 has no Sleeper row, so he is null with a reason and the next player fills in
  assert.strictEqual(w14.points, 107);
  assert.ok(/no Sleeper projection for week 14/.test(reasonOf(w14, "fk-wa3")));
  assert.strictEqual(w14.unavailable.find(u => u.player_id === "fk-wa3").points, null);
  assert.ok(!starters(w14).some(s => s.endsWith("fk-wa3")));
  // K and DEF are not projected: listed, not counted, and the kicker never appears as a starter
  assert.deepStrictEqual(r.basis.slots_not_projected, ["K", "DEF"]);
  assert.ok(!w12.lineup.some(l => l.slot === "K"));
});

test("weekly Out is out for its report week only; questionable plays; empty QB and SUPER_FLEX are flagged", () => {
  const r = run();
  const w12 = wk(r, "2", 12), w13 = wk(r, "2", 13);
  assert.ok(/Out on the week 12 injury report/.test(reasonOf(w12, "fk-qb1")));
  assert.ok(/^bye/.test(reasonOf(w12, "fk-qb2")));
  assert.deepStrictEqual(w12.flags.empty_slots.sort(), ["QB", "SUPER_FLEX"]);
  assert.strictEqual(w12.points, 48);
  assert.ok(starters(w12).includes("WR:fk-wr2"));             // questionable: counted
  assert.strictEqual(w13.points, 79);
  assert.deepStrictEqual(w13.flags.uncertain_return.map(u => u.player_id), ["fk-qb1"]);
  assert.ok(starters(w13).includes("QB:fk-qb1") && starters(w13).includes("SUPER_FLEX:fk-qb2"));
});

test("an IR player with no return week uses the provider's weeks, flagged uncertain", () => {
  const r = run(d => { d.injuries[0].return_week = null; });
  const w12 = wk(r, "1", 12);
  assert.ok(starters(w12).includes("TE:fk-ta2"));
  assert.ok(/no expected return week/.test(w12.flags.uncertain_return[0].reason));
  assert.strictEqual(w12.points, 106);   // 96 + ta2's 10 in the empty TE slot
});

test("ESPN cross-check: its own lineup beside Sleeper, never blended", () => {
  const r = run();
  const w12 = wk(r, "1", 12), w14 = wk(r, "1", 14);
  assert.strictEqual(w12.cross_check.source, "espn");
  assert.strictEqual(w12.cross_check.points, 89);     // same seven starters, each 1 lower
  // team 1's ESPN rows have no sleeper_id (as 74% of live ESPN rows): they join through player_key and the Sleeper rows
  assert.strictEqual(w12.cross_check.diff, 7);
  assert.strictEqual(w12.points, 96);                 // the Sleeper figure is unchanged by ESPN
  assert.strictEqual(w14.cross_check.points, null);
  assert.ok(/no ESPN projections for week 14/.test(w14.cross_check.reason));
  assert.strictEqual(w14.cross_check.diff, null);
  assert.strictEqual(r.sources.espn.rows_without_player_id, 1);
  const none = run(null, {crossCheck: null});
  assert.strictEqual(wk(none, "1", 12).cross_check, null);
  assert.strictEqual(wk(none, "1", 12).points, 96);
});

test("a provider 0 is a value, not missing", () => {
  const r = run(d => d.projections.forEach(p => { if (p.source === "sleeper" && p.sleeper_id === "fk-wa3") p.points_half_ppr = 0; }));
  const w12 = wk(r, "1", 12);
  assert.ok(starters(w12).includes("FLEX:fk-wa3"));
  assert.strictEqual(w12.points, 88);
  assert.deepStrictEqual(w12.flags.empty_slots, ["TE"]);
});

test("scoring format picks the stored column; the points function is one swappable function", () => {
  assert.strictEqual(wk(run(d => { d.scoring = "ppr"; }), "1", 13).points, 99 + 8);
  assert.strictEqual(wk(run(d => { d.scoring = "standard"; }), "1", 13).points, 99 - 8);
  // a stand-in for JEG-1688 rescoring: points from the stat line only
  const calls = [];
  const r = run(null, {points: (row, ctx) => { calls.push(ctx); return row.stats ? row.stats.rec_yd / 10 : null; }});
  assert.strictEqual(wk(r, "1", 13).points, 99);
  assert.ok(calls.every(c => c.scoring === "half_ppr" && typeof c.week === "number" && typeof c.source === "string"));
  assert.strictEqual(wk(r, "1", 13).cross_check.points, 0);   // ESPN rows have no stats here: every row null, every slot empty
  assert.ok(/ESPN row has no half_ppr points/.test(reasonOf(wk(r, "1", 13).cross_check, "fk-qa1")));
  assert.strictEqual(r.basis.points, "opts.points");
});

test("week 18 carries the rest-starters flag; weeks past 18 are capped", () => {
  const r = run(d => d.projections.forEach(p => { if (p.target_week === 14 && p.source === "sleeper") d.projections.push(Object.assign({}, p, {target_week: 18})); }),
    {fromWeek: 17, lastWeek: 19});
  assert.deepStrictEqual(r.window.weeks, [17, 18]);
  assert.ok(/capped at week 18/.test(r.window.source));
  assert.strictEqual(wk(r, "1", 18).flags.rest_starters_risk, true);
  assert.strictEqual(wk(r, "1", 17).flags.rest_starters_risk, false);
  assert.strictEqual(wk(r, "1", 18).flags.bye_unknown, true);   // no schedule rows for week 18 in the fixture
  assert.strictEqual(wk(r, "1", 18).points, 107);
});

test("window derivation from playoff spots, and missing inputs give a reason", () => {
  const st = n => { const s = clone(SMALL.state); s.playoff_rules.spots.value = n; return s; };
  assert.strictEqual(WTP.window(st(4)).last, 16);
  assert.strictEqual(WTP.window(st(6)).last, 17);
  assert.strictEqual(WTP.window(st(12)).last, 18);
  const noRules = clone(SMALL.state); noRules.playoff_rules.spots = LS.missing("not entered");
  assert.ok(/last playoff week is unknown/.test(WTP.window(noRules).reason));
  assert.strictEqual(WTP.window(noRules, {lastWeek: 16}).last, 16);
  const r = WTP.project(noRules, inputsOf(SMALL));
  assert.strictEqual(r.ok, false); assert.ok(r.reason);
  assert.ok(/scoring format/.test(run(d => { d.scoring = "tep"; }).reason));
  const noRoster = run(d => { delete d.rosters["2"]; });
  assert.ok(wk(noRoster, "2", 12).points === null && /no roster/.test(wk(noRoster, "2", 12).reason));
});

test("exact lineup where greedy fails (overlapping WRRB_FLEX and REC_FLEX)", () => {
  const best = WTP.bestLineup(["WRRB_FLEX", "REC_FLEX"], [{id: "w", pos: "WR", points: 10}, {id: "r", pos: "RB", points: 8}, {id: "t", pos: "TE", points: 2}]);
  assert.strictEqual(best.points, 18);   // greedy (best player first into the first slot) gives 12
  assert.deepStrictEqual(best.lineup.map(l => l.slot + ":" + l.player_id), ["WRRB_FLEX:r", "REC_FLEX:w"]);
});

function brute(slots, players) {
  const st = slots.filter(s => WTP.ELIGIBLE[s]);
  let best = 0;
  (function go(i, used, sum) {
    if (i === st.length) { if (sum > best) best = sum; return; }
    go(i + 1, used, sum);   // leave empty
    players.forEach((p, j) => { if (!used[j] && WTP.ELIGIBLE[st[i]].includes(p.pos)) { used[j] = true; go(i + 1, used, sum + p.points); used[j] = false; } });
  })(0, [], 0);
  return Math.round(best * 100) / 100;
}

test("best lineup equals brute force on 300 random rosters (superflex and mixed flex)", () => {
  let seed = 1658;
  const rand = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  const SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "WRRB_FLEX", "REC_FLEX"];
  const POS = ["QB", "RB", "WR", "TE"];
  for (let k = 0; k < 300; k++) {
    const slots = Array.from({length: 2 + Math.floor(rand() * 5)}, () => SLOTS[Math.floor(rand() * SLOTS.length)]);
    const players = Array.from({length: 1 + Math.floor(rand() * 7)}, (_, i) => ({id: "p" + i, pos: POS[Math.floor(rand() * 4)], points: Math.round(rand() * 3000) / 100}));
    const got = WTP.bestLineup(slots, players);
    assert.strictEqual(got.points, brute(slots, players), JSON.stringify({slots, players}));
    const ids = got.lineup.filter(l => l.player_id).map(l => l.player_id);
    assert.strictEqual(new Set(ids).size, ids.length, "a player starts twice");
    got.lineup.forEach(l => { if (l.player_id) assert.ok(WTP.ELIGIBLE[l.slot].includes(l.pos)); });
  }
});

test("Sleeper producer league (recorded superflex league, fake player ids): every team and week projected", () => {
  const live = fx("sleeper-live/full.json");
  const m = {}; Object.keys(live.matchups).forEach(k => { m[k] = live.matchups[k]; });
  const state = SL.buildLeagueState(live.league, live.users, live.rosters, m, {now: "2026-11-16T18:00:00Z"});
  assert.deepStrictEqual(LS.validate(state).errors, []);
  // swap the recorded players for fake ones: 2 QB, 4 RB, 4 WR, 2 TE per team, points varied by team and week
  const POS = ["QB", "QB", "RB", "RB", "RB", "RB", "WR", "WR", "WR", "WR", "TE", "TE"];
  const rosters = clone(live.rosters).map(r => Object.assign(r, {players: POS.map((_, i) => "fake-" + r.roster_id + "-" + i), taxi: ["fake-" + r.roster_id + "-11"]}));
  const projections = [];
  rosters.forEach(r => POS.forEach((pos, i) => { for (let w = 10; w <= 18; w++) {
    projections.push({source: "sleeper", as_of: "2026-11-16T13:30:00Z", target_week: w, source_player_id: "fake-" + r.roster_id + "-" + i, sleeper_id: "fake-" + r.roster_id + "-" + i,
      position: pos, team: "T" + i, points_ppr: 5 + ((r.roster_id * 7 + i * 3 + w) % 17), points_half_ppr: null, points_std: null, scoring_basis: "sleeper:pts_* as given"});
  } }));
  const settings = SL.settingsOf(live.league);
  assert.strictEqual(settings.superflex, true);
  const inputs = {rosters: WTP.rostersFromSleeper(rosters), slots: live.league.roster_positions, scoring: settings.scoring, projections, schedule: null, injuries: []};
  assert.ok(!inputs.rosters["1"].includes("fake-1-11"), "taxi squad is left out");
  const res = WTP.project(state, inputs);
  assert.strictEqual(res.ok, true, res.reason);
  assert.deepStrictEqual(res.window.weeks, [10, 11, 12, 13, 14, 15, 16, 17]);   // through 9 + 1; start 15, 6 spots = 3 rounds
  assert.strictEqual(res.teams.length, 12);
  res.teams.forEach(t => t.weeks.forEach(w => {
    assert.strictEqual(typeof w.points, "number", t.team_id + " week " + w.week);
    assert.strictEqual(w.flags.bye_unknown, true);
    assert.strictEqual(w.lineup.length, 9);   // QB, RB x2, WR x3, TE, FLEX, SUPER_FLEX
    const pool = inputs.rosters[t.team_id].map(id => { const p = projections.find(x => x.sleeper_id === id && x.target_week === w.week); return {id, pos: p.position, points: p.points_ppr}; });
    assert.strictEqual(w.points, brute(live.league.roster_positions, pool));
    assert.strictEqual(w.cross_check.points, null);   // no ESPN rows passed: null with a reason
  }));
});

test("module is pure: no network, clock or DOM", () => {
  const src = fs.readFileSync(path.join(ROOT, "app", "next", "weekly-team-projection.js"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  ["fetch(", "XMLHttpRequest", "Date(", "Date.now", "document.", "localStorage", "Math.random"].forEach(s => assert.ok(!src.includes(s), s));
});

(async () => {
  for (const [name, fn] of queue) {
    try { await fn(); passed++; console.log("ok   " + name); } catch (e) { failed++; console.log("FAIL " + name + "\n     " + (e && e.message)); }
  }
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
