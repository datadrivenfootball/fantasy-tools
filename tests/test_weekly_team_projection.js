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

test("bye, out player back per ESPN, TE at FLEX and missing week: team 1", () => {
  const r = run();
  const w12 = wk(r, "1", 12), w13 = wk(r, "1", 13), w14 = wk(r, "1", 14);
  // week 12: DDD on bye (ra3, ta1); ta2 is Out and ESPN projects him 0, so the TE slot is empty; qa2 fills SUPER_FLEX
  assert.strictEqual(w12.points, 96);
  assert.deepStrictEqual(w12.flags.empty_slots, ["TE"]);
  assert.ok(/^bye \(DDD/.test(reasonOf(w12, "fk-ra3")));
  assert.ok(/^bye \(DDD/.test(reasonOf(w12, "fk-ta1")));
  assert.ok(/ESPN projects 0 for week 12 \(first week above 0: 13\)/.test(reasonOf(w12, "fk-ta2")));
  assert.ok(starters(w12).includes("SUPER_FLEX:fk-qa2"));
  // week 13: LAR (nflverse LA) on bye; ta2 back (ESPN above 0) and flagged; a TE (ta1 9.5) beats the RB (ra3 9) at FLEX
  assert.strictEqual(w13.points, 99.5);
  assert.ok(/^bye \(LA /.test(reasonOf(w13, "fk-wa1")));
  assert.deepStrictEqual(w13.flags.uncertain_return.map(u => u.player_id), ["fk-ta2"]);
  assert.ok(/ESPN projects him from week 13/.test(w13.flags.uncertain_return[0].reason));
  assert.ok(starters(w13).includes("TE:fk-ta2") && starters(w13).includes("FLEX:fk-ta1"));
  // week 14: past ESPN's weeks, so ta2 uses the Sleeper weeks (flagged); wa3 has no Sleeper row: null, next player fills in
  assert.strictEqual(w14.points, 107.5);
  assert.ok(/ESPN has no week 14, so the Sleeper weeks are used/.test(w14.flags.uncertain_return[0].reason));
  assert.ok(/no Sleeper projection for week 14/.test(reasonOf(w14, "fk-wa3")));
  assert.strictEqual(w14.unavailable.find(u => u.player_id === "fk-wa3").points, null);
  assert.ok(!starters(w14).some(s => s.endsWith("fk-wa3")));
  // K and DEF are not projected: listed, not counted, and the kicker never appears as a starter
  assert.deepStrictEqual(r.basis.slots_not_projected, ["K", "DEF"]);
  assert.ok(!w12.lineup.some(l => l.slot === "K"));
});

test("out players, team 2: ESPN 0 then above 0, all-zero ESPN, no ESPN row (fallback); questionable plays", () => {
  const r = run();
  const w12 = wk(r, "2", 12), w13 = wk(r, "2", 13), w14 = wk(r, "2", 14);
  assert.ok(/ESPN projects 0 for week 12/.test(reasonOf(w12, "fk-qb1")));
  assert.ok(/^bye/.test(reasonOf(w12, "fk-qb2")));
  [w12, w13, w14].forEach(w => assert.ok(/ESPN projects 0 in every week/.test(reasonOf(w, "fk-wr4")), "wr4 week " + w.week));
  assert.ok(starters(w12).includes("RB:fk-rb3"));             // no ESPN row: Sleeper weeks, flagged
  assert.ok(/no ESPN row for him, so the Sleeper weeks are used/.test(w12.flags.uncertain_return.find(u => u.player_id === "fk-rb3").reason));
  assert.deepStrictEqual(w12.flags.empty_slots, ["QB"]);
  assert.strictEqual(w12.points, 59);
  assert.ok(starters(w12).includes("WR:fk-wr2"));             // questionable: counted, no flag
  assert.ok(!w12.flags.uncertain_return.some(u => u.player_id === "fk-wr2"));
  assert.strictEqual(w13.points, 85);
  assert.deepStrictEqual(w13.flags.uncertain_return.map(u => u.player_id).sort(), ["fk-qb1", "fk-rb3"]);
  assert.ok(starters(w13).includes("QB:fk-qb1") && starters(w13).includes("SUPER_FLEX:fk-qb2"));
  assert.strictEqual(w14.points, 85);
});

test("IR with no ESPN week above 0 uses the Sleeper weeks, flagged; a weekly Out with the same rows stays out", () => {
  const r = run(d => { d.injuries.find(j => j.sleeper_id === "fk-wr4").status = "IR"; });
  const w12 = wk(r, "2", 12);
  assert.ok(starters(w12).includes("WR:fk-wr4"));
  assert.ok(/IR with no ESPN week above 0, so the Sleeper weeks are used/.test(w12.flags.uncertain_return.find(u => u.player_id === "fk-wr4").reason));
  assert.strictEqual(w12.points, 74);   // RB 11 + 10, WR 20 + 12, TE 6, FLEX 9, SUPER_FLEX 6
  assert.ok(/ESPN projects 0 in every week/.test(reasonOf(wk(run(), "2", 12), "fk-wr4")));
});

test("a bye is not read as an out week: ESPN's bye 0 is a bye, and the player is back after it", () => {
  const r = run(d => { d.injuries.push({sleeper_id: "fk-ra3", status: "Out", week: 11, source: "test"}); });
  const w12 = wk(r, "1", 12), w13 = wk(r, "1", 13);
  assert.ok(/^bye \(DDD/.test(reasonOf(w12, "fk-ra3")));    // ESPN 0 there because of the bye
  assert.ok(!w13.unavailable.some(u => u.player_id === "fk-ra3"), "ra3 is available in week 13 (ESPN 8)");
  // without a schedule the bye cannot be seen, so ESPN's 0 that week reads as out (bye_unknown is flagged on the week)
  const noBye = run(d => { d.injuries.push({sleeper_id: "fk-ra3", status: "Out", week: 11, source: "test"}); d.schedule = null; });
  assert.ok(/ESPN projects 0 for week 12 \(first week above 0: 13\)/.test(reasonOf(wk(noBye, "1", 12), "fk-ra3")));
});

test("a team with source rows for the week but no usable projection for any player is null with a reason, not 0", () => {
  // Codex P1 on PR #1474: team 1's Sleeper rows removed, team 2's kept; the week still has rows, so it was a silent 0
  const r = run(d => { d.projections = d.projections.filter(p => !(p.source === "sleeper" && d.rosters["1"].includes(p.sleeper_id))); });
  [12, 13, 14].forEach(w => {
    const t1 = wk(r, "1", w);
    assert.strictEqual(t1.points, null, "team 1 week " + w);
    assert.ok(/no usable Sleeper projection fills/.test(t1.reason), t1.reason);
    assert.ok(wk(r, "2", w).points > 0, "team 2 week " + w + " is still scored");
  });
  // a partly missing roster: the next player fills in, and only a slot that a missing player could have filled
  // (with no one real left for it) makes the week null; team 1 week 13 loses its only TE rows (ta1, ta2)
  const te = run(d => { d.projections = d.projections.filter(p => !(p.source === "sleeper" && p.target_week === 13 && ["fk-ta1", "fk-ta2"].includes(p.sleeper_id))); });
  const w13 = wk(te, "1", 13);
  assert.strictEqual(w13.points, null);
  assert.ok(/TE/.test(w13.reason), w13.reason);
  // an empty slot from real unavailability (bye, out) stays a real 0 with the slot listed: team 2 week 12 QB
  assert.strictEqual(wk(te, "2", 12).points, 59);
  assert.deepStrictEqual(wk(te, "2", 12).flags.empty_slots, ["QB"]);
  // a roster with nobody on it has nothing to score: null, not 0
  const empty = run(d => { d.rosters["1"] = []; });
  assert.strictEqual(wk(empty, "1", 12).points, null);
  assert.ok(/no players/.test(wk(empty, "1", 12).reason));
});

test("an Out report applies from its report week on, never to earlier weeks in the window", () => {
  // Codex P2 on PR #1474: a week-13 report must not exclude the player from week 12
  const r = run(d => {
    d.injuries.find(j => j.sleeper_id === "fk-wr4").week = 13;   // ESPN 0 every week: out every week from 13
    d.injuries.find(j => j.sleeper_id === "fk-ta2").week = 13;   // ESPN 0 in week 12 only
  });
  const t2w12 = wk(r, "2", 12), t1w12 = wk(r, "1", 12);
  assert.ok(!t2w12.unavailable.some(u => u.player_id === "fk-wr4"), "wr4 counts in week 12, before his report");
  assert.ok(!t2w12.flags.uncertain_return.some(u => u.player_id === "fk-wr4"));
  assert.ok(/ESPN projects 0 in every week/.test(reasonOf(wk(r, "2", 13), "fk-wr4")));
  assert.ok(/ESPN projects 0 in every week/.test(reasonOf(wk(r, "2", 14), "fk-wr4")));
  assert.ok(!t1w12.unavailable.some(u => u.player_id === "fk-ta2"), "ta2 counts in week 12, before his report");
  assert.ok(starters(t1w12).includes("TE:fk-ta2"));
  // the report week itself and after: Jeremy's 2026-11-16 ESPN rule unchanged
  assert.deepStrictEqual(wk(r, "1", 13).flags.uncertain_return.map(u => u.player_id), ["fk-ta2"]);
});

test("ESPN cross-check: its own lineup beside Sleeper, never blended", () => {
  const r = run();
  const w12 = wk(r, "1", 12), w14 = wk(r, "1", 14);
  assert.strictEqual(w12.cross_check.source, "espn");
  assert.strictEqual(w12.cross_check.points, 89);     // same seven starters, each 1 lower
  assert.strictEqual(wk(r, "1", 13).cross_check.points, 91.5);
  assert.strictEqual(wk(r, "1", 13).cross_check.diff, 8);
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
  assert.strictEqual(wk(run(d => { d.scoring = "ppr"; }), "1", 13).points, 99.5 + 8);
  assert.strictEqual(wk(run(d => { d.scoring = "standard"; }), "1", 13).points, 99.5 - 8);
  // a stand-in for JEG-1688 rescoring: points from the stat line only
  const calls = [];
  const r = run(null, {points: (row, ctx) => { calls.push(ctx); return row.stats ? row.stats.rec_yd / 10 : null; }});
  assert.strictEqual(wk(r, "1", 13).points, 99.5);   // ESPN rows give no points here, so out players fall back to Sleeper weeks
  assert.ok(calls.every(c => c.scoring === "half_ppr" && typeof c.week === "number" && typeof c.source === "string"));
  // ESPN rows have no stats here: every row null, so the ESPN figure is missing (null), never 0 (Codex P1 on PR #1474)
  assert.strictEqual(wk(r, "1", 13).cross_check.points, null);
  assert.ok(/no usable ESPN projection fills/.test(wk(r, "1", 13).cross_check.reason));
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
  assert.strictEqual(wk(r, "1", 18).points, 107.5);
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

test("a TE starts at FLEX when he is the best one left", () => {
  const best = WTP.bestLineup(["TE", "FLEX"], [{id: "t1", pos: "TE", points: 10}, {id: "t2", pos: "TE", points: 8}, {id: "r", pos: "RB", points: 3}]);
  assert.deepStrictEqual(best.lineup.map(l => l.slot + ":" + l.player_id), ["TE:t1", "FLEX:t2"]);
  assert.strictEqual(best.points, 18);
});

test("exact lineup where greedy fails (overlapping WRRB_FLEX and REC_FLEX)", () => {
  const best = WTP.bestLineup(["WRRB_FLEX", "REC_FLEX"], [{id: "w", pos: "WR", points: 10}, {id: "r", pos: "RB", points: 8}, {id: "t", pos: "TE", points: 2}]);
  assert.strictEqual(best.points, 18);   // greedy (best player first into the first slot) gives 12
  assert.deepStrictEqual(best.lineup.map(l => l.slot + ":" + l.player_id), ["WRRB_FLEX:r", "REC_FLEX:w"]);
});

// The brute force has its own eligibility table, so a wrong table in the module cannot also pass here.
const BRUTE_ELIGIBLE = {QB: ["QB"], RB: ["RB"], WR: ["WR"], TE: ["TE"], FLEX: ["RB", "WR", "TE"], WRRB_FLEX: ["RB", "WR"],
  REC_FLEX: ["WR", "TE"], SUPER_FLEX: ["QB", "RB", "WR", "TE"]};
function brute(slots, players) {
  const st = slots.filter(s => BRUTE_ELIGIBLE[s]);
  let best = 0;
  (function go(i, used, sum) {
    if (i === st.length) { if (sum > best) best = sum; return; }
    go(i + 1, used, sum);   // leave empty
    players.forEach((p, j) => { if (!used[j] && BRUTE_ELIGIBLE[st[i]].includes(p.pos)) { used[j] = true; go(i + 1, used, sum + p.points); used[j] = false; } });
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
    got.lineup.forEach(l => { if (l.player_id) assert.ok(BRUTE_ELIGIBLE[l.slot].includes(l.pos)); });
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
