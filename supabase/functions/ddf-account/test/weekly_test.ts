// deno-lint-ignore-file require-await -- the deps interface is async; these fakes have nothing to await
// Hermetic tests for the weekly read (weekly.ts) and the staging planner (staging/account/weekly.js), JEG-1736.
//   deno test --allow-read supabase/functions/ddf-account/test/
import { assert, assertAlmostEquals, assertEquals } from "jsr:@std/assert@1";
import { buildWeekly, fetchEspnKdef, leagueWeeks, type KdefRow, type ScheduleGame, type WarehouseRow, type XwalkRow } from "../weekly.ts";

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
  assertEquals(wk.players["470.p.103"].weeks[14], { points: 7.5, source: "sleeper", bye: false, note: null }); // no ESPN row that week
  assertEquals(wk.players["470.p.106"].weeks[14], { points: 0, source: "espn", bye: true, note: "BYE" }); // MIA bye
  assertEquals(wk.players["470.p.107"].weeks[13], { points: 8, source: "espn_live", bye: false, note: null });
  assertEquals(wk.players["470.p.107"].match, "team");
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
  // by hand: team 1 starters wk13 = QB 23 + WRa 17.25 + WRb 13.8 + RB 16.1 + TE 10.35 + flex WRc 12.65 + K 8 + DEF 6 = 107.15
  assertAlmostEquals(g13.mine.total, 107.15, 0.06);
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
  assert(["seed_game", "free"].includes(g13.type), g13.type);
  assert(!g13.goals.includes("playoffs"));
  assert(g13.moves.some((m: { kind: string }) => m.kind === "add"), "FA WR (16) beats the team's WRc in week 13");
  assert(g13.moves.some((m: { kind: string; text: string }) => m.kind === "add" && m.text === "Add FA K (K, 12.0); drop K1"), "FA K 12 beats K1 8, and K1 is then the free drop");
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
  assertEquals(k.best_add.name, "FA K");
  assertEquals(k.cost[13], 8);
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
  assert(r.adds.some((a: { name: string; drop: { name: string } }) => a.name === "FA K" && a.drop.name === "K1"));
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
  assertEquals(got.players, [{ espn_id: "-16019", name: "Giants D/ST", pos: "DEF", team: "NYG", weeks: { 15: 8.1 } }]);
});
