// deno-lint-ignore-file require-await -- the deps interface is async; these fakes have nothing to await
// Hermetic tests for the weekly read (weekly.ts) and the staging planner (staging/account/weekly.js), JEG-1736.
//   deno test --allow-read supabase/functions/ddf-account/test/
import { assert, assertAlmostEquals, assertEquals } from "jsr:@std/assert@1";
import { leagueRules, rescore } from "../scoring.ts";
import { buildWeekly, etIso, fetchEspnKdef, leagueWeeks, type KdefRow, type ScheduleGame, type WarehouseRow, type XwalkRow } from "../weekly.ts";

const ROOT = new URL("../../../../", import.meta.url);
await import(new URL("staging/account/weekly.js", ROOT).href);
// deno-lint-ignore no-explicit-any
const W = (globalThis as any).DDFWeekly;

// A 4-team Yahoo league, weeks 13-14 regular, 15-16 playoffs (4 spots).
const SLOTS = ["QB", "WR", "WR", "RB", "TE", "W/R/T", "K", "DEF", "BN", "BN", "IR"];
const p = (id: number, name: string, position: string, nfl_team: string, slot = "BN", status: string | null = null) =>
  ({ player_id: `470.p.${id}`, name, position, nfl_team, slot, status });
type R = ReturnType<typeof p>;
function team(n: number, wins: number, roster: R[]) {
  return { team_key: `470.l.1.t.${n}`, name: `Team ${n}`, managers: [], standings: { wins, losses: 12 - wins, ties: 0, points_for: 1200 + n, points_against: 1200, rank: n, rank_source: "test" }, faab_remaining: 50, waiver_priority: n, roster };
}
function league() {
  const roster = (n: number) => [
    p(n * 100 + 1, `QB${n}`, "QB", "KC", "QB"), p(n * 100 + 2, `WR${n}a`, "WR", "KC", "WR"), p(n * 100 + 3, `WR${n}b`, "WR", "BUF", "WR"),
    p(n * 100 + 4, `RB${n}`, "RB", "BUF", "RB"), p(n * 100 + 5, `TE${n}`, "TE", "KC", "TE"), p(n * 100 + 6, `RB${n}b`, "RB", "MIA", "W/R/T"),
    p(n * 100 + 7, `K${n}`, "K", "DAL", "K"), p(n * 100 + 8, `DEF${n}`, "DEF", "MIN", "DEF"), p(n * 100 + 9, `WR${n}c`, "WR", "MIA", "BN", n === 1 ? "Q" : null),
  ];
  const mu = (wk: number, a: number, b: number, pa: number, pb: number, wa: number | null) =>
    ({ team_keys: [`470.l.1.t.${a}`, `470.l.1.t.${b}`], points: [null, null], projected_points: [pa, pb], win_probability: wa === null ? [null, null] : [wa, 1 - wa], is_playoffs: wk > 14, status: "not_started" });
  return {
    shape: "ddf-connected-league/0", source: { kind: "flaim" }, platform: "yahoo", league_key: "470.l.1", season: 2026, name: "Test League",
    pulled_at: "2026-11-27T12:00:00Z", current_week: 13, my_team_key: "470.l.1.t.1",
    settings: { num_teams: 4, ddf: { scoring: "half_ppr", superflex: false, teams: 8, roster: {} }, roster_positions: SLOTS, playoff_start_week: 15, playoff_teams: 4, last_regular_week: 14, trade_deadline: { week: null, date: null, none: true, source: null }, waiver_type: "faab", faab_budget: 100 },
    teams: [team(1, 8, roster(1)), team(2, 7, roster(2)), team(3, 5, roster(3)), team(4, 4, roster(4))],
    schedule: [
      { week: 12, matchups: [{ ...mu(12, 1, 2, 110, 100, 1), status: "final", points: [120, 90] }] },
      { week: 13, matchups: [mu(13, 1, 2, 110, 100, 0.66), mu(13, 3, 4, 95, 105, 0.36)] },
      { week: 14, matchups: [mu(14, 1, 3, 120, 100, 0.79), mu(14, 2, 4, 100, 112, 0.31)] },
      { week: 15, matchups: [] }, { week: 16, matchups: [] },
    ],
    free_agents: [p(901, "FA WR", "WR", "NYJ"), p(902, "FA K", "K", "LV")],
    missing: [],
  };
}
// Every player: QB 20, WRa 15, WRb 12, RB 14, TE 9, RBb 10, WRc 11, K 8, DEF 6, scaled by team strength.
const BASE: Record<string, number> = { 1: 20, 2: 15, 3: 12, 4: 14, 5: 9, 6: 10, 9: 11 };
function deps(lg: ReturnType<typeof league>, opts: { kdefDown?: boolean } = {}) {
  const xw: XwalkRow[] = [];
  const rows: WarehouseRow[] = [];
  for (const t of lg.teams) for (const r of t.roster) {
    const id = r.player_id.split(".p.")[1], n = Number(id.slice(-1));
    if (r.position === "K" || r.position === "DEF") continue;
    xw.push([`s${id}`, `e${id}`, id, r.name, r.position, r.nfl_team]);
    const scale = 1 + (4 - Number(t.team_key.slice(-1))) * 0.05;
    for (const wk of [13, 14, 15, 16]) {
      if (id === "103" && wk === 14) continue; // team 1's WRb: no ESPN row in week 14, Sleeper has one
      rows.push({ source: "espn", as_of: "2026-11-27T12:40:00Z", target_week: wk, source_player_id: `e${id}`, sleeper_id: null, team: r.nfl_team, position: r.position, points_std: null, points_half_ppr: BASE[n] * scale, points_ppr: null });
    }
    rows.push({ source: "sleeper", as_of: "2026-11-27T13:30:00Z", target_week: 14, source_player_id: `s${id}`, sleeper_id: `s${id}`, team: r.nfl_team, position: r.position, points_std: null, points_half_ppr: 7.5, points_ppr: null });
  }
  xw.push(["s901", "e901", "901", "FA WR", "WR", "NYJ"]);
  for (const wk of [13, 14, 15, 16]) rows.push({ source: "espn", as_of: "2026-11-27T12:40:00Z", target_week: wk, source_player_id: "e901", sleeper_id: null, team: "NYJ", position: "WR", points_std: null, points_half_ppr: 16, points_ppr: null });
  // nflverse schedule: MIA on bye in week 14 (its players are 0, BYE); every other team plays every week
  const teams = ["KC", "BUF", "MIA", "DAL", "MIN", "NYJ", "LV", "NE"];
  const sched: ScheduleGame[] = [];
  for (const wk of [13, 14, 15, 16]) {
    const playing = teams.filter((t) => !(wk === 14 && (t === "MIA" || t === "NE")));
    for (let i = 0; i < playing.length; i += 2) sched.push({ week: wk, home_team: playing[i], away_team: playing[i + 1], as_of: "2026-11-27T13:31:00Z" });
  }
  const kd: KdefRow[] = [
    { espn_id: "k1", name: "K1", pos: "K", team: "DAL", weeks: { 13: 8, 14: 8, 15: 8, 16: 8 } },
    { espn_id: "k2", name: "FA K", pos: "K", team: "LV", weeks: { 13: 12, 14: 12, 15: 12, 16: 12 } },
    { espn_id: "-16016", name: "Vikings D/ST", pos: "DEF", team: "MIN", weeks: { 13: 6, 14: 6, 15: 6, 16: 6 } },
  ];
  return {
    rows: async (_s: number, from: number, e: string[], s: string[]) => rows.filter((r) => r.target_week >= from && (r.source === "espn" ? e.includes(r.source_player_id) : s.includes(r.sleeper_id!))),
    schedule: async () => sched,
    xwalk: async () => xw,
    kdef: async () => (opts.kdefDown ? null : { as_of: "2026-11-27T14:00:00Z", players: kd }),
  };
}

Deno.test("weekly read: weeks run from the current week to the last playoff week", () => {
  assertEquals(leagueWeeks(league()), [13, 14, 15, 16]);
});

Deno.test("weekly read: ids join, ESPN first then Sleeper, byes are BYE, K/DEF from ESPN by team", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  assertEquals(wk.shape, "ddf-league-weekly/0");
  assertEquals(wk.weeks, [13, 14, 15, 16]);
  const qb = wk.players["470.p.101"];
  assertEquals(qb.sleeper_id, "s101");
  assertEquals(qb.weeks[13].source, "espn");
  assertAlmostEquals(qb.weeks[13].points, 20 * 1.15, 1e-9);
  assertEquals(wk.players["470.p.103"].weeks[14], { points: 7.5, source: "sleeper", bye: false, note: null, rescored: false }); // no ESPN row that week
  assertEquals(wk.players["470.p.106"].weeks[14], { points: 0, source: "espn", bye: true, note: "BYE", rescored: false }); // MIA bye
  assertEquals(wk.players["470.p.107"].weeks[13], { points: 8, source: "espn_live", bye: false, note: null, rescored: false });
  assertEquals(wk.players["470.p.107"].match, "team_name"); // the team's ESPN kicker with the same last name
  assertEquals(wk.players["470.p.108"].match, "team"); // one D/ST per team
  assertEquals(wk.players["470.p.108"].espn_id, "-16016");
  assertEquals(wk.players["470.p.902"].weeks[13].points, 12); // a free-agent kicker
  assertEquals(wk.byes.MIA, [14]);
  assertEquals(wk.unmatched, []);
});

Deno.test("weekly read: missing is null with a reason, never 0", async () => {
  const lg = league();
  const d = deps(lg, { kdefDown: true }); // the id lists are built before the rookie joins
  lg.teams[0].roster.push(p(999, "Unknown Rookie", "RB", "KC"));
  const wk = await buildWeekly(lg, d);
  assertEquals(wk.players["470.p.999"].weeks[13], { points: null, source: null, bye: false, note: "Not matched by id" });
  assert(wk.unmatched.some((u) => u.player_id === "470.p.999"));
  assertEquals(wk.players["470.p.107"].weeks[13].points, null); // ESPN K/DEF read failed
  assert(wk.unmatched.some((u) => u.player_id === "470.p.107" && /could not be read/.test(u.reason)));
});

Deno.test("planner math: win chance, fitted spread, best lineup with flex and empty slots", () => {
  assertAlmostEquals(W.winChance(0, 20), 0.5, 1e-7);
  assertAlmostEquals(W.winChance(20, 20), 0.7602, 1e-3); // phi(20 / (20 * sqrt 2))
  assertAlmostEquals(W.phi(1.96), 0.975, 1e-3);
  const fit = W.fitSpread(league());
  assert(fit.n === 4, fit.basis);
  assert(fit.sd > 12 && fit.sd < 40);
  const l = W.lineup(["QB", "RB", "W/R/T", "K"], [
    { player_id: "a", name: "A", pos: "QB", points: 20 }, { player_id: "b", name: "B", pos: "RB", points: 9 },
    { player_id: "c", name: "C", pos: "WR", points: 14 }, { player_id: "d", name: "D", pos: "RB", points: 12 },
  ]);
  assertEquals(l.starters.map((s: { player_id: string | null }) => s.player_id), ["a", "d", "c", null]);
  assertEquals(l.total, 46); // the empty K slot is a real 0 when no one could fill it
  assertEquals(l.empty_slots, ["K"]);
  const blocked = W.lineup(["QB", "K"], [{ player_id: "a", name: "A", pos: "QB", points: 20 }, { player_id: "k", name: "K", pos: "K", points: null, note: "Not matched" }]);
  assertEquals(blocked.total, null); // a missing kicker who would start makes the week unscored, not 0
});

Deno.test("planner: games, wins distribution, bracket, goals and moves", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  const plan = W.plan(lg, wk, { runs: 4000 });
  assertEquals(plan.games.map((g: { week: number }) => g.week), [13, 14, 15, 16]);
  const g13 = plan.games[0];
  assertEquals(g13.opp.name, "Team 2");
  // by hand: team 1 starters wk13 = QB 23 + WRa 17.25 + WRb 13.8 + RB 16.1 + TE 10.35 + flex WRc 12.65 + DEF 6
  // + K: the waiver kicker (top-4 average = FA K, 12) beats K1 (8), so the assumed pickup starts = 111.15
  assertAlmostEquals(g13.mine.total, 111.15, 0.06);
  assertEquals(g13.win.yahoo, 0.66);
  assertAlmostEquals(g13.win.ddf, W.winChance(g13.mine.total - g13.theirs.total, plan.spread.sd), 1e-3);
  const dist = plan.wins.dist.reduce((a: number, d: { p: number }) => a + d.p, 0);
  assertAlmostEquals(dist, 1, 1e-2);
  assertEquals(plan.wins.games, 2);
  assert(plan.sim.playoff_p >= 0.9, "an 8-4 leader of a 4-team league with 4 spots is in");
  assertEquals(plan.games[2].phase, "playoffs");
  assert(plan.games[2].likely.length > 0);
  // all four teams make a 4-spot bracket, so week 13 cannot move the playoff odds: it is about the seed
  assertEquals(plan.sim.playoff_p, 1);
  assertEquals(g13.stake.playoffs, 0);
  assert(["seed_game", "free"].includes(g13.type), g13.type); // labels stay, with the stake beside them (Jeremy, 2026-11-27)
  assert(!g13.goals.includes("playoffs"));
  assert(g13.moves.some((m: { kind: string }) => m.kind === "add"), "FA WR (16) beats the team's WRc in week 13");
  assert(g13.moves.some((m: { kind: string; text: string }) => m.kind === "assumed" && /kicker from waivers: counted at the top-1 average, 12\.0/.test(m.text)), "K is an assumed waiver pickup, not a call-out");
  assert(!g13.moves.some((m: { kind: string; text: string }) => m.kind === "add" && /FA K/.test(m.text)));
  assert(g13.moves.some((m: { kind: string }) => m.kind === "start"), "WRc on the bench outscores RBb in the flex");
  const g14 = plan.games[1];
  assert(g14.mine.starters.every((s: { name: string | null }) => s.name !== "RB1b" && s.name !== "WR1c"), "a bye player does not start");
  assert(g14.mine.bench.some((b: { name: string; bye: boolean }) => b.name === "RB1b" && b.bye));
  assertEquals(g14.mine.empty_slots, ["W/R/T"]); // both flex options are on bye: an empty slot, a real 0
  assert(plan.need[0].startsWith("8-4, 1st."));
  assertEquals(plan.goals.map((g: { id: string }) => g.id), ["high_score", "record", "seed", "playoffs"]);
});

Deno.test("cover: cost by week, who covers, holes first, K/DEF row with the best add", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  const c = W.cover(lg, wk, "470.l.1.t.1");
  assertEquals(c.weeks, [13, 14, 15, 16]);
  const qb = c.starters.find((s: { name: string }) => s.name === "QB1");
  assertEquals(qb.kind, "hole"); // no backup QB: losing him leaves the slot empty
  assertAlmostEquals(qb.weeks[13].cost, 23, 0.06);
  assertEquals(qb.weeks[13].cover, null);
  const rb = c.starters.find((s: { name: string }) => s.name === "RB1");
  // week 13: RB1 out -> RB1b moves to RB, WR1c stays in flex... the player who enters is RB1b
  assertEquals(rb.weeks[13].cover.name, "RB1b");
  assertAlmostEquals(rb.weeks[13].cost, 16.1 - 11.5, 0.06);
  assertEquals(c.starters[0].kind, "hole");
  const k = c.kdef.find((x: { pos: string }) => x.pos === "K");
  assertEquals(k.starter.name, "K1");
  assertEquals(k.backup, null);
  assertEquals(k.best_add.name, "Waiver average (top 4)");
  assertEquals(k.best_add.weeks[13], 12);
  assertEquals(k.cost[13], 0); // K1 (8) is below the waiver average (12): losing him costs nothing
});

Deno.test("trade impact: both sides by week, the game against the partner counts on both sides", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  const t = W.tradeImpact(lg, wk, "470.l.1.t.1", "470.l.1.t.2", ["470.p.105"], ["470.p.205"]); // TE1 for TE2
  assertEquals(t.sides[0].name, "Team 1");
  assertAlmostEquals(t.sides[0].delta[13], 9 * 1.1 - 9 * 1.15, 0.06);
  assertAlmostEquals(t.sides[1].delta[13], 9 * 1.15 - 9 * 1.1, 0.06);
  const g13 = t.games.find((g: { week: number }) => g.week === 13);
  assert(g13.is_partner);
  assert(g13.win_after < g13.win_before);
  const te = t.players.find((p: { name: string }) => p.name === "TE2");
  assertEquals(te.to_team, "Team 1");
  assert(te.weeks[13].starts_after);
});

Deno.test("recommendations: adds and trades ranked by weekly gain, moves in time order", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  const plan = W.plan(lg, wk, { runs: 2000 });
  const r = W.recommendations(lg, wk, "470.l.1.t.1", { plan });
  assertEquals(r.adds[0].name, "FA WR"); // 16 a week beats the bench every week
  assert(!r.adds.some((a: { pos: string }) => a.pos === "K"), "a kicker no better than the waiver average is not a pickup");
  for (let i = 1; i < r.adds.length; i++) assert(r.adds[i - 1].total_gain >= r.adds[i].total_gain);
  for (let i = 1; i < r.trades.length; i++) assert(r.trades[i - 1].my_total >= r.trades[i].my_total);
  assert(r.trades.every((t: { my_total: number; their_total: number }) => t.my_total >= 2 && t.their_total >= -1));
  for (let i = 1; i < r.moves_in_time.length; i++) assert(r.moves_in_time[i - 1].when_sort <= r.moves_in_time[i].when_sort);
  const g = W.recommendations(lg, wk, "470.l.1.t.1", { plan, sort: "games" });
  for (let i = 1; i < g.trades.length; i++) assert((g.trades[i - 1].my_weighted || 0) >= (g.trades[i].my_weighted || 0));
});

Deno.test("ESPN K/DEF read keeps this season's weekly projections only (ESPN also sends last season's)", async () => {
  const body = { players: [{ player: { id: -16019, fullName: "Giants D/ST", defaultPositionId: 16, proTeamId: 19, stats: [
    { scoringPeriodId: 15, statSourceId: 1, statSplitTypeId: 1, seasonId: 2026, appliedTotal: 8.1 },
    { scoringPeriodId: 15, statSourceId: 1, statSplitTypeId: 1, seasonId: 2025, appliedTotal: 4.44 },
    { scoringPeriodId: 15, statSourceId: 0, statSplitTypeId: 1, seasonId: 2025, appliedTotal: 5 },
  ] } }] };
  const got = await fetchEspnKdef(async () => new Response(JSON.stringify(body), { status: 200 }), 2026, new Date("2026-11-27T12:00:00Z"));
  assertEquals(got.players.map((x) => ({ ...x, lines: undefined })), [{ espn_id: "-16019", name: "Giants D/ST", pos: "DEF", team: "NYG", weeks: { 15: 8.1 }, lines: undefined }]);
});

Deno.test("review fixes: a kicker needs his name, an empty ESPN read fails, kickoff times are Eastern", async () => {
  const lg = league();
  lg.teams[0].roster[6] = p(107, "New Kicker", "K", "DAL", "K"); // DAL's ESPN kicker is K1: not him
  const wk = await buildWeekly(lg, deps(lg));
  assertEquals(wk.players["470.p.107"].weeks[13].points, null);
  assert(wk.unmatched.some((u) => u.player_id === "470.p.107"));
  let threw = false;
  try { await fetchEspnKdef(async () => new Response(JSON.stringify({ players: [] }), { status: 200 }), 2026, new Date()); } catch { threw = true; }
  assert(threw, "an empty ESPN list is not a success (it would be cached for 6 hours)");
  assertEquals(etIso("2026-11-27", "16:30"), "2026-11-27T21:30:00.000Z"); // EST
  assertEquals(etIso("2026-10-04", "13:00"), "2026-10-04T17:00:00.000Z"); // EDT
});

Deno.test("review fixes: reserve slots never start; exact lineup when flex slots do not nest", () => {
  const S = { settings: { roster_positions: ["RB", "W/R", "W/T"] } };
  const players = [{ player_id: "r", name: "R", pos: "RB", points: 10 }, { player_id: "w", name: "W", pos: "WR", points: 12 }, { player_id: "t", name: "T", pos: "TE", points: 5 }, { player_id: "r2", name: "R2", pos: "RB", points: 1 }];
  const l = W.lineup(W.slotsOf(S), players);
  assertEquals(l.total, 27); // RB 10, W/R W 12, W/T T 5 (greedy would put W in W/T and leave 23)
  const wk = { weeks: [13], players: { a: { weeks: { 13: { points: 20, source: "espn", bye: false, note: null } } }, b: { weeks: { 13: { points: 9, source: "espn", bye: false, note: null } } } } };
  const t = W.teamWeek({ settings: { roster_positions: ["RB"] } }, wk, [{ player_id: "a", name: "Taxi Rookie", position: "RB", slot: "TAXI" }, { player_id: "b", name: "Bench RB", position: "RB", slot: "BN" }], 13);
  assertEquals(t.starters[0].name, "Bench RB");
});

Deno.test("review fixes: the live week counts the score so far plus the open slots; no title odds without the bracket", async () => {
  const lg = league();
  lg.current_week = 13;
  const m = lg.schedule[1].matchups[0]; // Team 1 v Team 2, week 13
  m.status = "live"; m.points = [40, 10];
  const wk = await buildWeekly(lg, deps(lg));
  // KC played already (Thursday); everyone else plays Sunday
  wk.kickoffs = { 13: { KC: "2026-11-26T18:00:00Z", BUF: "2026-11-29T18:00:00Z", MIA: "2026-11-29T18:00:00Z", DAL: "2026-11-29T18:00:00Z", MIN: "2026-11-29T18:00:00Z", NYJ: "2026-11-29T18:00:00Z", LV: "2026-11-29T18:00:00Z" } };
  lg.pulled_at = "2026-11-27T19:00:00Z";
  const plan = W.plan(lg, wk, { runs: 2000, now: "2026-11-27T20:00:00Z" });
  const g = plan.games[0];
  assert(g.mine.live);
  assertEquals(g.mine.banked, 40);
  // Team 1 open slots after QB, WRa, TE (KC, played) lock: WR WRb 13.8, RB 16.1, flex WRc 12.65, K (waiver avg) 12, DEF 6 = 60.55
  assertAlmostEquals(g.mine.total, 100.55, 0.06);
  assert(g.win.ddf > W.winChance(g.mine.total - g.theirs.total, plan.spread.sd), "less still to play: a lead is safer than a full-week spread says");
  assert(!g.moves.some((mv: { kind: string; text: string }) => mv.kind === "watch" && /WR1a|QB1/.test(mv.text)));
  const short = league(); short.current_week = 16; // final week: one round of a two-round bracket left
  const wk2 = await buildWeekly(short, deps(short));
  const p2 = W.plan(short, wk2, { runs: 500 });
  assertEquals(p2.sim.title_p, null);
});

const USO_RULES = [["4", 0.04], ["5", 4], ["6", -1], ["9", 0.1], ["10", 6], ["11", 0.5], ["12", 0.1], ["13", 6], ["15", 6], ["16", 2], ["18", -2], ["19", 3], ["20", 3], ["21", 3], ["22", 4], ["23", 5], ["29", 1], ["32", 1], ["33", 2], ["34", 2], ["35", 6], ["36", 2], ["37", 2], ["49", 6], ["50", 10], ["51", 7], ["52", 4], ["53", 1], ["54", 0], ["55", -1], ["56", -4]]
  .map(([statId, value]) => ({ statId, value, displayName: "s" + statId }));

Deno.test("rescoring: ESPN and Sleeper stat lines and ESPN K/DEF lines with the league's own settings (hand-checked)", () => {
  const r = leagueRules({ settings: { scoring_raw: USO_RULES } })!;
  // Josh Allen, ESPN, week 13: 258.6496*.04 + 1.555*4 - .8029 + 30.4064*.1 + .7576*6 = 23.35 (ESPN standard said 22.55: Int -2)
  const allen = rescore("espn", { passing_yards: 258.6496, passing_tds: 1.555, interceptions: 0.8029, rushing_yards: 30.4064, rushing_tds: 0.7576, receptions: 0, receiving_yards: 0, receiving_tds: 0 }, r)!;
  assertAlmostEquals(allen.points, 23.35, 0.01);
  assert(allen.missing.includes("s16") && allen.missing.includes("s18")); // ESPN's line has no 2-pt or fumbles
  const sl = rescore("sleeper", { pass_yd: 251.69, pass_td: 1.32, pass_int: 0.81, rush_yd: 31.52, rush_td: 0.89, fum_lost: 0.19, pass_2pt: 0.1, rush_2pt: 0.07 }, r)!;
  assertAlmostEquals(sl.points, 251.69 * 0.04 + 1.32 * 4 - 0.81 + 3.152 + 0.89 * 6 - 0.38 + 0.34, 0.01);
  // Jason Sanders, week 15: .463*5 + .611*4 + 1.303*3 + 2.384 = 11.05 (ESPN default 10.73 charges missed FGs)
  assertAlmostEquals(rescore("K", { 74: 0.463, 77: 0.611, 80: 1.303, 85: 0.322, 86: 2.384, 88: 0.049 }, r)!.points, 11.05, 0.01);
  // Giants D/ST, week 15 (ESPN default 8.1): sacks, INT, fumbles, TDs, safety, blocks, return TDs and points-allowed bands
  const g = { 89: 0.016, 90: 0.07, 91: 0.235, 92: 0.2, 93: 0.007, 94: 0.093, 95: 0.677, 96: 0.464, 97: 0.112, 98: 0.016, 99: 3.765, 101: 0.008, 102: 0.025, 121: 0.145, 122: 0.185, 123: 0.11, 124: 0.035, 125: 0.004 };
  assertAlmostEquals(rescore("DEF", g, r)!.points, 8.73, 0.02);
  // missed FGs by distance (ESPN splits them): -1 under 40, -1 40-49, 0 50+
  const r2 = leagueRules({ settings: { scoring_raw: [{ statId: "24", value: -1 }, { statId: "25", value: -1 }, { statId: "26", value: -1 }, { statId: "27", value: -1 }, { statId: "28", value: 0 }] } })!;
  assertAlmostEquals(rescore("K", { 76: 0.16, 79: 0.11, 82: 0.02, 85: 0.29 }, r2)!.points, -0.13, 0.001);
  assertEquals(leagueRules({ settings: { scoring_raw: null } }), null);
});

Deno.test("rescoring: the weekly read marks every number rescored or not, and says so", async () => {
  const lg = league();
  const plain = await buildWeekly(lg, deps(lg));
  assertEquals(plain.scoring_basis.rescored, false);
  assert(/not your league's/.test(plain.scoring_basis.text));
  (lg.settings as Record<string, unknown>).scoring_raw = USO_RULES;
  const d = deps(lg);
  const rows0 = d.rows;
  d.rows = async (...a: Parameters<typeof rows0>) => (await rows0(...a)).map((x) => ({ ...x, stats: x.source === "espn" ? { receptions: 2, receiving_yards: 20 } : null }));
  const wk = await buildWeekly(lg, d);
  assertEquals(wk.scoring_basis.rescored, true);
  assertEquals(wk.players["470.p.102"].weeks[13], { points: 3, source: "espn", bye: false, note: null, rescored: true }); // 2*.5 + 20*.1
  assertEquals(wk.players["470.p.107"].weeks[13].rescored, false); // the fake ESPN K has no stat line: default scoring, labelled
});

Deno.test("review fixes 2: advice uses the current time; a game in progress keeps the rest of its projection; other pages skip the live week", async () => {
  const lg = league();
  lg.current_week = 13;
  const m = lg.schedule[1].matchups[0];
  m.status = "live"; m.points = [40, 10];
  lg.pulled_at = "2026-11-29T17:30:00Z";
  const wk = await buildWeekly(lg, deps(lg));
  wk.kickoffs = { 13: { KC: "2026-11-29T18:00:00Z", BUF: "2026-11-29T21:00:00Z", MIA: "2026-11-29T21:00:00Z", DAL: "2026-11-29T21:00:00Z", MIN: "2026-11-29T21:00:00Z", NYJ: "2026-11-29T21:00:00Z", LV: "2026-11-29T21:00:00Z" } };
  // pulled before KC kicked off, viewed while KC plays: KC players are not movable any more, so no advice names them
  const p = W.plan(lg, wk, { runs: 500, now: "2026-11-29T18:30:00Z" });
  const g = p.games[0];
  assert(g.moves.every((mv: { text: string }) => !/QB1|WR1a|TE1/.test(mv.text)), JSON.stringify(g.moves));
  // pulled mid-game (KC 1 hour in): the rest of their projections still count
  lg.pulled_at = "2026-11-29T19:00:00Z";
  const q = W.plan(lg, wk, { runs: 500, now: "2026-11-29T19:00:00Z" });
  const left = 2.5 / 3.5, kc = (20 + 15 + 9) * 1.15;
  assertAlmostEquals(q.games[0].mine.still_to_come, 13.8 + 16.1 + 12.65 + 12 + 6 + kc * left, 0.1);
  // cover, trade impact and recommendations count from next week once the current week has kicked off
  assertEquals(W.cover(lg, wk, "470.l.1.t.1", { now: "2026-11-29T19:00:00Z" }).weeks, [14, 15, 16]);
  assertEquals(W.recommendations(lg, wk, "470.l.1.t.1", { now: "2026-11-29T19:00:00Z" }).weeks, [14, 15, 16]);
  assertEquals(W.cover(lg, wk, "470.l.1.t.1", { now: "2026-11-29T12:00:00Z" }).weeks, [13, 14, 15, 16]);
});

Deno.test("recommendations: who else a pickup helps, with their FAAB (context, not a bid)", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  const r = W.recommendations(lg, wk, "470.l.1.t.1", {});
  const fa = r.adds.find((a: { name: string }) => a.name === "FA WR");
  assert(fa.rivals.length > 0);
  assert(fa.rivals.every((x: { team_key: string; gain: number; faab: number }) => x.team_key !== "470.l.1.t.1" && x.gain >= 1 && x.faab === 50));
  for (let i = 1; i < fa.rivals.length; i++) assert(fa.rivals[i - 1].gain >= fa.rivals[i].gain);
  assertEquals(r.me, { faab: 50, waiver_priority: 1, faab_budget: 100 });
});

Deno.test("every staging page script parses", async () => {
  const dir = new URL("staging/account/", ROOT);
  for await (const f of Deno.readDir(dir)) {
    if (!f.name.endsWith(".js")) continue;
    const src = await Deno.readTextFile(new URL(f.name, dir));
    try { new Function(src); } catch (e) { throw new Error(f.name + ": " + (e as Error).message); }
  }
});

Deno.test("JEG-1737 rule A: an opponent keeps his set lineup with holes filled; Yahoo only this week; stakes priced", async () => {
  const lg = league();
  // Team 2 (week 13 opponent) has a bye RB in his set flex slot: MIA on bye in week 14 is RB2b (slot W/R/T)
  const wk = await buildWeekly(lg, deps(lg));
  const p = W.plan(lg, wk, { runs: 2000, payouts: { title: 500, high_score_week: 50 } });
  const g14 = p.games.find((g: { week: number }) => g.week === 14); // v Team 3
  const theirs = g14.theirs;
  assertEquals(theirs.rule, "set_filled");
  // Team 3's set lineup: RB3b (MIA, bye wk14) in W/R/T is a hole; his best bench player for the flex is WR3c (MIA, bye) -> empty?
  const flex = theirs.starters.find((x: { slot: string }) => x.slot === "W/R/T");
  assert(flex.player_id === null || flex.name !== "RB3b", "a bye starter is replaced");
  assert(theirs.filled.some((f: { slot: string; out: string }) => f.slot === "W/R/T" && f.out === "RB3b"));
  // set lineup, holes filled, never better than the best lineup
  const best = W.teamWeek(lg, wk, lg.teams[2].roster, 14);
  assert(theirs.total <= best.total + 1e-9);
  // Yahoo's number only for the current week (13)
  assertEquals(p.games[0].win.yahoo, 0.66);
  assertEquals(g14.win.yahoo, null);
  assertEquals(g14.yahoo_proj, null);
  // stakes: with a title payout given (old shape), the stake is the change in expected prize money, in dollars
  const s13 = p.games[0].stake;
  assert(typeof s13.dollars === "number" && /^\$/.test(s13.text), s13.text);
  assertEquals(s13.unpriced, []);
  assertAlmostEquals(p.games[0].high_score.expected_dollars, 50 * p.games[0].high_score.chance, 0.01);
  // a playoff game has a stake too (title and runner-up)
  assert(p.games.filter((g: { phase: string }) => g.phase === "playoffs").some((g: { stake: { dollars: number | null } }) => typeof g.stake.dollars === "number"));
});

Deno.test("review fixes 3: no title stake without the bracket; partner rows use the set lineup", async () => {
  const lg = league();
  (lg.settings as Record<string, unknown>).playoff_teams = 5; // no bracket DDF can play out
  const wk = await buildWeekly(lg, deps(lg));
  const p = W.plan(lg, wk, { runs: 1000 });
  assertEquals(p.sim.title_p, null);
  assert(/only best record counts/.test(p.games[0].stake.text), p.games[0].stake.text);
  const t = W.tradeImpact(league(), wk, "470.l.1.t.1", "470.l.1.t.2", ["470.p.105"], ["470.p.205"]);
  assertEquals(t.sides[1].rule, "set");
  assertEquals(t.sides[0].rule, "best");
});

Deno.test("rulings 2026-11-27 (2): K/DEF waiver average for us and opponents; playoff score to clear; waiver money", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  const p = W.plan(lg, wk, { runs: 3000 });
  // an opponent's set K (K2, 8) is below the waiver average (12): his slot takes the assumed pickup too
  const theirs = p.games[0].theirs;
  const k = theirs.starters.find((x: { slot: string }) => x.slot === "K");
  assert(k.assumed && k.points === 12, JSON.stringify(k));
  // playoff games carry the score to clear: median, with an 80% range around it
  const po = p.games.filter((g: { phase: string }) => g.phase === "playoffs");
  for (const g of po) {
    assert(g.target && g.target.low <= g.target.score && g.target.score <= g.target.high, JSON.stringify(g.target));
    assert(g.target.score > 50 && g.target.score < 200);
  }
  // waiver money: every team's FAAB, most first, mine marked
  assertEquals(p.faab.length, 4);
  assert(p.faab.some((f: { me: boolean; faab: number }) => f.me && f.faab === 50));
});

Deno.test("review fixes 4: the assumed waiver pickup is never a start move or a bench row", async () => {
  const lg = league();
  const wk = await buildWeekly(lg, deps(lg));
  const p = W.plan(lg, wk, { runs: 500 });
  const g13 = p.games[0]; // K1 (8) is below the waiver average (12): the assumed kicker starts
  assert(g13.mine.starters.some((x: { assumed: boolean }) => x.assumed));
  assert(!g13.moves.some((m: { kind: string; text: string }) => m.kind === "start" && /Waiver/.test(m.text)), JSON.stringify(g13.moves));
  for (const g of p.games) for (const l of [g.mine, g.theirs]) if (l) assert(!(l.bench || []).some((x: { assumed: boolean }) => x.assumed));
});

Deno.test("payouts (USO, from league emails): places 1-4, a 3rd-place game, high score through a week, no best-record goal", async () => {
  const lg = league();
  (lg.settings as Record<string, unknown>).payouts = { source: "from league emails, 2024-25", place: { 1: 450, 2: 300, 3: 200, 4: 100 }, high_score_week: 50, high_score_through_week: 14, best_record: 0 };
  const wk = await buildWeekly(lg, deps(lg));
  const p = W.plan(lg, wk, { runs: 3000 });
  // every team makes a 4-team bracket, so the least anyone wins is $100 and the expected money is between $100 and $450
  assert(p.money.expected >= 100 && p.money.expected <= 450, String(p.money.expected));
  const last = p.games[p.games.length - 1];
  assert(/the 3rd-place game in \d+%/.test(last.opp_note), last.opp_note);
  assert(/final: \$150, 3rd-place game: \$100/.test(last.stake.text), last.stake.text);
  const semi = p.games[p.games.length - 2];
  assert(semi.stake.dollars > 0 && semi.stake.dollars <= 350, String(semi.stake.dollars)); // final ($300-450) v 3rd-place game ($100-200)
  assertEquals(p.goals.map((g: { id: string }) => g.id), ["high_score", "seed", "playoffs"]); // no record prize, no goal
  assert(typeof p.games.find((g: { week: number }) => g.week === 14).high_score.expected_dollars === "number");
  assert(p.games.find((g: { week: number }) => g.week === 15).high_score.no_payout); // weeks after 14 pay no high score here
  assert(/Payouts \(from league emails, 2024-25\): 1st \$450, 2nd \$300, 3rd \$200, 4th \$100/.test(p.sources.join(" ")), p.sources.join(" "));
});

Deno.test("payouts review: equal 3rd/4th pay both semifinal losers; playoff $/pt scales by the chance to reach the game", async () => {
  const lg = league();
  (lg.settings as Record<string, unknown>).payouts = { place: { 1: 450, 2: 300, 3: 100, 4: 100 }, high_score_week: 50, high_score_through_week: 14 };
  const wk = await buildWeekly(lg, deps(lg));
  const p = W.plan(lg, wk, { runs: 3000 });
  assert(p.money.expected >= 100, String(p.money.expected)); // all four teams make it: nobody can finish with $0
  const semi = p.games.find((g: { week: number }) => g.week === 15);
  assert(semi.stake.dollars <= 350, String(semi.stake.dollars)); // final ($300-450) v a tied 3rd ($100)
  // the second team in a 2-team bracket reaches the final only some of the time: its playoff points are worth the stake times that chance
  const lg2 = league();
  (lg2.settings as Record<string, unknown>).playoff_teams = 2;
  (lg2.settings as Record<string, unknown>).payouts = { place: { 1: 450, 2: 300 } };
  const p2 = W.plan(lg2, await buildWeekly(lg2, deps(lg2)), { runs: 3000, myTeamKey: "470.l.1.t.2" });
  const fin = p2.games.find((g: { week: number }) => g.week === 15);
  assert(fin.reach > 0.05 && fin.reach < 0.95, String(fin.reach));
  const sdd = Math.sqrt(2) * p2.spread.sd, dens = Math.exp(-0.5 * Math.pow(fin.margin / sdd, 2)) / (sdd * Math.sqrt(2 * Math.PI));
  assertAlmostEquals(fin.dollars_per_point, fin.reach * fin.stake.dollars * dens, 0.02);
});
