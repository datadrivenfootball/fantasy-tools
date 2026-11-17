// test_league_state_wiring.js — JEG-1685 (part of JEG-1653): league-state/1 wired into the league workspace, ddf-state and
// the ES-12 week settings. Contract: docs/contract/league-state-v1.md. No live calls, no DOM.
// Run: node tests/test_league_state_wiring.js
// 1. Workspace round trip: leagueState survives normalize -> serialize -> parseStored; a workspace saved before the field
//    (or a paste / manual league) reads as null with a reason, never an empty object or zeros.
// 2. ddf-state round trip: block encode -> decode keeps it; an old state without it stays valid and gains nothing; a bad
//    one is dropped with a warning; the URL query never carries it.
// 3. ES-12 fill: known start week fills; a value the reader set wins; a value an earlier import filled is replaced;
//    unknown weeks (manual / pre-draft) fill nothing and say why.
// 4. Sleeper import by default: load(id, {leagueState: true}) output goes through record() into the pasted record.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
globalThis.DDFRosterPaste = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
require(path.join(ROOT, "app", "next", "rosterparse.js"));
require(path.join(ROOT, "app", "next", "league-paste.js"));
const LS = require(path.join(ROOT, "app", "next", "league-state.js"));
const SL = require(path.join(ROOT, "app", "next", "sleeper-import.js"));
const WS = require(path.join(ROOT, "app", "v2", "workspace.js"));
const CODEC = require(path.join(ROOT, "app", "v2", "ddf-state.js"));
const live = n => JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "sleeper-live", n + ".json"), "utf8"));
const fx = n => JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "league-state", n + ".json"), "utf8"));
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const ROWS = TABLE.map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });
const NOW = "2026-11-16T18:00:00Z";
const clone = x => JSON.parse(JSON.stringify(x));

// A Sleeper league whose playoffs start in week `start` (last regular week start - 1), built by the real producer.
function sleeperState(start) {
  const d = clone(live("full"));
  if (start !== undefined) d.league.settings.playoff_week_start = start;
  const last = d.league.settings.playoff_week_start - 1;
  const m = {};
  Object.keys(d.matchups).forEach(k => { if (Number(k) <= last) m[k] = d.matchups[k]; });
  return SL.buildLeagueState(d.league, d.users, d.rosters, m, {now: NOW});
}
const DEF = {regularEnd: 14, playoffLo: 15, playoffHi: 17};
const wsWith = extra => Object.assign({id: "league_1", name: "L", teams: [{id: "t1", name: "A", entries: []}], myTeamId: "t1"}, extra || {});
const roundTrip = ws => WS.parseStored(JSON.stringify({v: 1, workspaces: [ws], activeId: ws.id}));

let passed = 0, failed = 0;
const queue = [];
function test(name, fn) { queue.push([name, fn]); }

test("fixtures the tests rely on validate", () => {
  assert.deepStrictEqual(LS.validate(sleeperState()).errors, []);
  assert.deepStrictEqual(LS.validate(sleeperState(14)).errors, []);
});

/* ---- 1. workspace ---- */
test("workspace round trip keeps the league-state object and the weeks it filled", () => {
  const ls = sleeperState();
  const w = WS.normalizeWorkspace(wsWith({leagueState: ls, weeksFilled: {regularEnd: 14, playoffLo: 15, playoffHi: 17}}));
  const back = roundTrip(w);
  assert.strictEqual(back.status, "ok");
  assert.deepStrictEqual(back.workspace.leagueState, ls);
  assert.strictEqual(back.workspace.leagueStateReason, null);
  assert.deepStrictEqual(back.workspace.weeksFilled, {regularEnd: 14, playoffLo: 15, playoffHi: 17});
  assert.deepStrictEqual(LS.validate(back.workspace.leagueState).errors, []);
});
test("workspace saved before the field reads null with a reason, never zero or empty", () => {
  const back = roundTrip(wsWith());
  assert.strictEqual(back.status, "ok");
  assert.strictEqual(back.workspace.leagueState, null);
  assert.ok(/no season state/i.test(back.workspace.leagueStateReason));
  assert.strictEqual(back.workspace.weeksFilled, null);
  assert.strictEqual(back.workspace.teams.length, 1);
});
test("an unreadable league-state in a workspace is dropped to null with a reason; the league itself loads", () => {
  [{version: "league-state/2", teams: []}, "text", [], 0].forEach(bad => {
    const w = WS.normalizeWorkspace(wsWith({leagueState: bad, leagueStateReason: "kept reason"}));
    assert.strictEqual(w.leagueState, null);
    assert.strictEqual(w.leagueStateReason, "kept reason");
    assert.strictEqual(w.weeksFilled, null);
  });
});
test("a stored reason survives the round trip for a paste or manual league", () => {
  const reason = "A pasted league has no season state (records, schedule, playoff rules): the paste drops them.";
  const back = roundTrip(wsWith({leagueState: null, leagueStateReason: reason}));
  assert.strictEqual(back.workspace.leagueState, null);
  assert.strictEqual(back.workspace.leagueStateReason, reason);
});
test("other workspace operations keep the league-state", () => {
  const ls = sleeperState();
  let w = WS.normalizeWorkspace(wsWith({leagueState: ls}));
  w = WS.ops ? WS.ops.rename(w, "Renamed") : Object.assign({}, w, {name: "Renamed"});
  assert.deepStrictEqual(roundTrip(w).workspace.leagueState, ls);
});

/* ---- 2. ddf-state ---- */
const league = {scoring: "ppr", teams: 12};
test("ddf-state block round trip carries the league-state", () => {
  const ls = sleeperState();
  const block = CODEC.encodeBlock({v: 1, league, leagueState: ls});
  const back = CODEC.decodeBlock(block);
  assert.deepStrictEqual(back.warnings, []);
  assert.deepStrictEqual(back.state.leagueState, ls);
  assert.deepStrictEqual(LS.validate(back.state.leagueState).errors, []);
  assert.strictEqual(back.state.league.scoring, "ppr");
});
test("an old state without league-state stays valid and gains nothing", () => {
  const old = '```ddf-state\n{"v":1,"league":{"scoring":"ppr","teams":12},"work":{"view":"targets"}}\n```';
  const r = CODEC.decodeBlock(old);
  assert.deepStrictEqual(r.warnings, []);
  assert.ok(r.state && !("leagueState" in r.state));
  assert.ok(!/leagueState/.test(CODEC.encodeBlock(r.state)));
  assert.ok(CODEC.decodeQuery("scoring=ppr&teams=12&v=1").state);
});
test("a bad league-state is dropped with a warning; the rest of the state still reads", () => {
  [{version: "league-state/9", league: {}, teams: [{}]}, {version: "league-state/1", league: {}, teams: []}, "x", []].forEach(bad => {
    const r = CODEC.normalize({v: 1, league, leagueState: bad});
    assert.ok(!("leagueState" in r.state));
    assert.ok(r.warnings.some(w => /leagueState/.test(w)));
    assert.strictEqual(r.state.league.scoring, "ppr");
  });
  const huge = sleeperState(); huge.padding = "x".repeat(70000);
  const r = CODEC.normalize({v: 1, league, leagueState: huge});
  assert.ok(!("leagueState" in r.state) && r.warnings.some(w => /too large/.test(w)));
});
test("the URL query never carries the league-state", () => {
  const q = CODEC.encodeQuery({v: 1, league, leagueState: sleeperState()});
  assert.ok(!/league-state|leagueState|schedule/.test(q));
  assert.ok(/scoring=ppr/.test(q));
});
test("league-state alone is not a usable state (a league or work is still required)", () => {
  const r = CODEC.normalize({v: 1, leagueState: sleeperState()});
  assert.strictEqual(r.state, null);
});

/* ---- 3. ES-12 week fill ---- */
test("known start week fills the weeks; last regular week is start - 1", () => {
  const f = LS.weekFill(sleeperState(14), DEF, DEF, null);
  assert.deepStrictEqual(f.patch, {regularEnd: 13, playoffLo: 14, playoffHi: 17});
  assert.strictEqual(f.why, null);
  assert.ok(/^sleeper:/.test(f.plan.source) && /^\d{4}-\d{2}-\d{2}T/.test(f.plan.as_of));
});
test("a league on the site standard weeks fills the same weeks (no change to any value)", () => {
  assert.deepStrictEqual(LS.weekFill(sleeperState(), DEF, DEF, null).patch, DEF);
});
test("a value the reader set or confirmed wins", () => {
  const set = {regularEnd: 13, playoffLo: 14, playoffHi: 16};
  const f = LS.weekFill(sleeperState(15), set, DEF, null);
  assert.strictEqual(f.patch, null);
  assert.ok(/reader/.test(f.why));
  // even one changed value (only the last playoff week) is the reader's
  assert.strictEqual(LS.weekFill(sleeperState(14), {regularEnd: 14, playoffLo: 15, playoffHi: 16}, DEF, null).patch, null);
});
test("weeks an earlier import filled are replaced by the next import; weeks changed after that are kept", () => {
  const first = LS.weekFill(sleeperState(14), DEF, DEF, null).patch;
  const again = LS.weekFill(sleeperState(16), first, DEF, first);
  assert.deepStrictEqual(again.patch, {regularEnd: 15, playoffLo: 16, playoffHi: 17});
  const edited = Object.assign({}, first, {playoffHi: 18});
  assert.strictEqual(LS.weekFill(sleeperState(16), edited, DEF, first).patch, null);
});
test("unknown weeks fill nothing and say why (manual league, pre-draft Sleeper, invalid state)", () => {
  const manual = fx("manual");
  manual.playoff_rules.start_week = LS.missing("not entered");
  manual.playoff_rules.last_regular_week = LS.missing("not entered");
  assert.deepStrictEqual(LS.validate(manual).errors, []);
  const f = LS.weekFill(manual, DEF, DEF, null);
  assert.strictEqual(f.patch, null);
  assert.strictEqual(f.why, "not entered");
  const p = live("preseason");
  const pre = SL.buildLeagueState(p.league, p.users, p.rosters, {}, {now: NOW});
  delete pre.playoff_rules.start_week.value; pre.playoff_rules.start_week = LS.missing("provider did not say");
  pre.playoff_rules.last_regular_week = LS.missing("start is unknown");
  assert.strictEqual(LS.weekFill(pre, DEF, DEF, null).patch, null);
  const bad = sleeperState(); bad.version = "league-state/2";
  assert.strictEqual(LS.weekFill(bad, DEF, DEF, null).patch, null);
  assert.strictEqual(LS.weekFill(null, DEF, DEF, null).patch, null);
});
test("weeks the engine cannot hold are not applied; nothing is invented for the last playoff week", () => {
  assert.strictEqual(LS.weekFill(sleeperState(), DEF, DEF, null).patch.playoffHi, 17);
  const late = sleeperState(); late.playoff_rules.start_week.value = 19; late.playoff_rules.last_regular_week.value = 18;
  late.record_through_week.value = 9; late.schedule = LS.missing("test"); 
  assert.strictEqual(LS.weekFill(late, DEF, DEF, null).patch, null);
  assert.strictEqual(LS.weekFill(sleeperState(), {regularEnd: 14, playoffLo: 15, playoffHi: 15}, {regularEnd: 14, playoffLo: 15, playoffHi: 15}, null).patch.playoffHi, 15);
  const lo16 = LS.weekFill(sleeperState(16), {regularEnd: 14, playoffLo: 15, playoffHi: 15}, {regularEnd: 14, playoffLo: 15, playoffHi: 15}, null);
  assert.strictEqual(lo16.patch, null);
  assert.ok(/after the engine/.test(lo16.why));
});

/* ---- 4. Sleeper import stores it by default (record) ---- */
const sys = require("child_process");
const PLAYERS = JSON.parse(sys.execFileSync("python3", ["-c",
  "import sys,json; sys.path.insert(0,'pipelines'); import build_root_pages as b; print(json.dumps(b.sleeper_players()))"], {cwd: ROOT}).toString());
function fakeFetch(map) {
  return url => {
    const hit = Object.keys(map).find(k => url.endsWith(k));
    if (hit === undefined) return Promise.resolve({ok: false, status: 404, json: () => Promise.resolve(null)});
    return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(map[hit])});
  };
}
function routes(fx) {
  const id = fx.league.league_id, m = {[`/league/${id}`]: fx.league, [`/league/${id}/users`]: fx.users, [`/league/${id}/rosters`]: fx.rosters, "/state/nfl": fx.state, "sleeper-players.json": PLAYERS};
  Object.keys(fx.matchups).forEach(w => { if (fx.matchups[w]) m[`/league/${id}/matchups/${w}`] = fx.matchups[w]; });
  return m;
}
function playable(fx) {
  const d = clone(fx), ids = Object.keys(PLAYERS.p).slice(0, 40);
  d.rosters.forEach((r, i) => { r.players = ids.slice(i * 3, i * 3 + 3); });
  return d;
}
test("Sleeper load with leagueState reaches the pasted record; a paste or manual record carries null with a reason", async () => {
  const d = playable(live("full"));
  const out = await SL.load(d.league.league_id, {fetch: fakeFetch(routes(d)), rows: ROWS, table: TABLE, leagueState: true, now: NOW});
  assert.ok(out.ok, JSON.stringify(out));
  out.result.leagueState = out.leagueState || null;
  const rec = global.DDF.leaguePaste.record(out.result, "sleeper");
  assert.ok(rec.leagueState && rec.leagueState.version === "league-state/1");
  assert.deepStrictEqual(LS.validate(rec.leagueState).errors, []);
  assert.strictEqual(rec.leagueStateReason, null);
  const paste = global.DDF.leaguePaste.record({teams: [], league: {}}, "paste");
  assert.strictEqual(paste.leagueState, null);
  assert.ok(paste.leagueStateReason && /paste/.test(paste.leagueStateReason));
  assert.strictEqual(paste.weeksFilled, null);
  const noState = global.DDF.leaguePaste.record({teams: [], league: {}}, "sleeper");
  assert.strictEqual(noState.leagueState, null);
  assert.ok(noState.leagueStateReason);
});
test("pasted record -> workspace -> ddf-state: one object end to end", () => {
  const ls = sleeperState(14);
  const rec = {leagueState: ls, leagueStateReason: null, weeksFilled: {regularEnd: 13, playoffLo: 14, playoffHi: 17}};
  const w = roundTrip(WS.normalizeWorkspace(wsWith(rec))).workspace;
  const block = CODEC.encodeBlock({v: 1, league, leagueState: w.leagueState});
  assert.deepStrictEqual(CODEC.decodeBlock(block).state.leagueState, ls);
});

(async () => {
  for (const [name, fn] of queue) {
    try { await fn(); passed++; console.log("ok  " + name); } catch (e) { failed++; console.log("FAIL " + name + "\n  " + (e && e.message || e)); }
  }
  console.log(`${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
