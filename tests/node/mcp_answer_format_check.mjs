// Connector walkthrough 2026-11-21 (Jeremy: "Do all recommendations", part B "clear, short answers"; decision 4A
// "Viable trades only, with a closest fallback when none"):
// - every reply opens with one plain line that answers the question, also structuredContent.summary (its first key);
// - the finders list acceptable trades by default, and the closest 1-2 with the check each fails when none pass;
// - name notices fold into one line each after the answer (kickers and defenses counted, not one line per name);
// - compare_trade speaks for the user (give/get, you win/lose) and adds the starting lineup change when the roster
//   is known; trade_targets finds the weakest starting slot for a team; risers_fallers says who has each player and
//   why a value went to 0 (from the trade charts, never an injury claim); an empty trade_targets says what to try.
// Stub get-values, no network. Run by tests/test_mcp_remote.py.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { evalPageModule, PAGE_MODULE_FILES } from "../../supabase/functions/mcp/analyses.ts";
import { setKnownKickers } from "../../supabase/functions/mcp/names.ts";

const require = createRequire(import.meta.url);
const codec = require("../../app/v2/ddf-state.js");
const finder = require("../../app/v2/finder.js");
const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const modules = Object.fromEntries(Object.entries(PAGE_MODULE_FILES).map(([name, m]) => [name, evalPageModule(read(`../../app/${m.file}`), name)]));
setKnownKickers(["Brandon McManus", "Chris Boswell", "Jake Bates"]);

// [key, name, pos, DDF Value, trade chart (Indexed) value]. Rico Runner is cheap on DDF Value and dear on the charts,
// so trading him for Trey McBride passes every check (their flex gains more than their TE loses on the charts).
const ROWS = [
  [1, "Josh Allen", "QB", 30, 30], [2, "Bijan Robinson", "RB", 40, 40], [3, "Jahmyr Gibbs", "RB", 30, 30],
  [4, "Rico Runner", "RB", 20, 40], [5, "Tyler Goodson", "RB", 10, 10], [6, "Justin Jefferson", "WR", 30, 30],
  [7, "Garrett Wilson", "WR", 25, 25], [8, "George Pickens", "WR", 20, 20], [9, "Hunter Henry", "TE", 1, 1],
  [10, "Jared Goff", "QB", 30, 30], [11, "Derrick Henry", "RB", 40, 40], [12, "Kyren Williams", "RB", 30, 30],
  [13, "James Cook", "RB", 20, 20], [14, "Rachaad White", "RB", 10, 10], [15, "Puka Nacua", "WR", 30, 30],
  [16, "Drake London", "WR", 25, 25], [17, "Chris Bell", "WR", 20, 20], [18, "Trey McBride", "TE", 21, 18],
  [19, "Noah Gray", "TE", 2, 2], [20, "Dalton Kincaid", "TE", 6, 6], [21, "Free Agent Guy", "WR", 3, 3],
  [22, "Bo Nix", "QB", 18, 18], [23, "Isaiah Likely", "TE", 9, 9],
];
const chart = (v) => ({ usatoday: v, fantasycalc: v, fantasypros: v, cbs: v });
// This week Bo Nix is at 0 on every chart (last week 18, projections still 9): a drop to 0 with a reason.
const now = (key, v) => (key === 22 ? 0 : v);
const rows = ROWS.map(([player_key, name, pos, value, market]) => ({
  player_key, name, pos, value: now(player_key, value), tier: "starter", chart_values: chart(now(player_key, value)),
  chart_indexed: chart(now(player_key, market)), ddf_value_charts: now(player_key, value), ddf_value_projections: player_key === 22 ? 9 : value,
}));
const base = (scoring, teams, superflex) => ({ attribution: "Data Driven Football", as_of: "2026-11-21", setting: { scoring, teams, superflex },
  players: [...rows].sort((a, b) => b.value - a.value), sources_included: ["usatoday", "fantasycalc", "fantasypros", "cbs"], sources_excluded: [], week: 11, default_week: 11, weeks: [11] });
const values = async (scoring, teams, superflex) => base(scoring, teams, superflex);
// include=series,prior: this week's series per player, and last week's (Free Agent Guy rose 3 -> 9 on the charts).
const series = Object.fromEntries(rows.map((p) => [String(p.player_key), { ddf_value: p.value, ddf_value_charts: p.value,
  ddf_value_projections: p.ddf_value_projections, ...chart(p.chart_indexed.cbs) }]));
const lastWeek = (k) => Object.fromEntries(ROWS.map(([key, , , value, market]) =>
  [String(key), k in chart(0) ? market : k === "ddf_value_projections" && key === 22 ? 9 : value]));
const priorSeries = Object.fromEntries(["ddf_value", "ddf_value_charts", "ddf_value_projections", "usatoday", "fantasycalc", "fantasypros", "cbs"]
  .map((k) => [k, { available: true, reason: null, values: lastWeek(k) }]));
// Free Agent Guy: last week 3 on DDF Value and the charts, 3 on projections; this week 9 (series) on DDF Value.
for (const k of ["ddf_value", "ddf_value_charts", "usatoday", "fantasycalc", "fantasypros", "cbs"]) priorSeries[k].values["21"] = 3;
priorSeries.ddf_value_projections.values["21"] = 3;
series["21"] = { ...series["21"], ddf_value: 9, ddf_value_charts: 9, ...chart(9) };
const fetchAnalysis = async (scoring, teams, superflex, league, week, includes) => ({
  ...base(scoring, teams, superflex),
  ...(includes.includes("series") ? { series } : {}),
  ...(includes.includes("prior") ? { prior: { available: true, reason: null, current_week: 11, prior_week: 10, series: priorSeries } } : {}),
});
const deps = { codec, siteOrigin: "https://site.test" };
const finderDeps = { finder, fetchCharts: values, analysis: { fetchAnalysis, modules } };
const call = async (name, args) => (await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: { scoring: "ppr", superflex: false, teams: 12, ...args } } },
  values, deps, finderDeps)).result;
const text = (r) => r.content[0].text;
const opensWithSummary = (r, label) => {
  assert.notEqual(r.isError, true, `${label}: ${text(r)}`);
  const s = r.structuredContent.summary;
  assert.equal(typeof s, "string", `${label}: summary`);
  assert.equal(Object.keys(r.structuredContent)[0], "summary", `${label}: summary is the first key`);
  assert.ok(text(r).startsWith(`${s}\n`), `${label}: the text opens with the summary`);
  assert.doesNotMatch(s, /\n/, `${label}: one line`);
  return s;
};

const MINE = "Josh Allen, Bijan Robinson, Jahmyr Gibbs, Rico Runner, Tyler Goodson, Justin Jefferson, Garrett Wilson, George Pickens, Hunter Henry, K Brandon McManus, DEF Seahawks";
const THEM = "Jared Goff, Derrick Henry, Kyren Williams, James Cook, Rachaad White, Puka Nacua, Drake London, Chris Bell, Trey McBride, Noah Gray, Chris Boswell, DEF Bengals";
const OTHER = "Bo Nix, Dalton Kincaid, Isaiah Likely, Jake Bates, Dolphins D/ST";
const league = [{ name: "Mine", players: MINE }, { name: "Team 10", players: THEM }, { name: "Team 4", players: OTHER }];

// ---------- every tool opens with one plain line ----------
let r = await call("get_values", { limit: 3 });
assert.match(opensWithSummary(r, "get_values"), /^Top players by DDF Value: Bijan Robinson 40, Derrick Henry 40, /);
assert.match(text(r), /^Top players.*\nData Driven Football\nAs of: 2026-11-21\nSettings: ppr, 12 teams\nWeek: 11/, "header and week come after the answer");
r = await call("explain", { topic: "tiers" });
assert.match(opensWithSummary(r, "explain"), /^Tier is where a player sits in the league/);

// ---------- compare_trade speaks for the user, with the lineup change when the roster is known ----------
r = await call("compare_trade", { give: "Hunter Henry, Rico Runner", get: "Trey McBride" });
assert.equal(opensWithSummary(r, "compare"), "Even by DDF Value (give 21.0, get 21.0).");
r = await call("compare_trade", { give: "Rico Runner", get: "Noah Gray" });
assert.equal(r.structuredContent.summary, "You lose 18.0 by DDF Value (give 20.0, get 2.0).");
assert.match(text(r), /\nYou give \(total 20\.0\):\n  Rico Runner \(RB\): 20\nYou get \(total 2\.0\):/);
assert.equal(r.structuredContent.lineup, undefined, "no roster, no lineup line");
// side_a/side_b still work, the same answer
assert.equal((await call("compare_trade", { side_a: "Rico Runner", side_b: "Noah Gray" })).structuredContent.summary, r.structuredContent.summary);
r = await call("compare_trade", { give: "Rico Runner", get: "Trey McBride", mine: MINE });
assert.equal(opensWithSummary(r, "compare+mine"), "Roughly even by DDF Value: you gain 1.0 (give 20.0, get 21.0).");
// Rico Runner left the flex; George Pickens (same value) takes it.
assert.match(text(r), /^Your starting lineup: \+20\.0 \(TE Hunter Henry 1 -> Trey McBride 21, FLEX Rico Runner 20 -> George Pickens 20\)\.$/m);
assert.deepEqual(r.structuredContent.lineup.changes[0], { pos: "TE", out: "Hunter Henry", out_value: 1, in: "Trey McBride", in_value: 21 });
// the roster from a league with my_team (or a state that saved it); a player you give who is not yours is named
r = await call("compare_trade", { give: "Puka Nacua", get: "Bo Nix", league_teams: league, my_team: "Mine" });
assert.match(text(r), /^Your starting lineup: \+0\.0 \(no starter changes\); not on your roster: Puka Nacua\.$/m);
// by_source: the chart count rides on the same line
r = await call("compare_trade", { give: "Rico Runner", get: "Noah Gray", by_source: true });
assert.equal(opensWithSummary(r, "by_source"), "You lose 18.0 by DDF Value (give 20.0, get 2.0). 4 of 4 charts agree.");
assert.match(text(r), /Series \| You give \| You get \| Net for you/);

// ---------- finders: acceptable trades first; the closest when none ----------
r = await call("find_trades", { mine: MINE, theirs: THEM });
let s = opensWithSummary(r, "find_trades");
assert.ok(r.structuredContent.trades.length > 0 && r.structuredContent.trades.every((t) => t.viable), "default lists acceptable trades only");
assert.equal(r.structuredContent.viable_only, true);
assert.match(s, /^\d+ trades? they would likely accept; best: give .+ for .+ \([+-]\d+\.\d for you\)\.$/);
assert.ok(r.structuredContent.trades.some((t) => t.userGives.some((p) => p.name === "Rico Runner") && t.userGets.some((p) => p.name === "Trey McBride")));
const all = await call("find_trades", { mine: MINE, theirs: THEM, viable_only: false, limit: 50 });
assert.ok(all.structuredContent.trades.some((t) => !t.viable), "viable_only=false keeps the full list");
assert.match(all.structuredContent.summary, /^\d+ trades found, \d+ they would likely accept; first: give /);
// none acceptable: say so, then the closest 1-2 with the check each fails, in plain words
r = await call("find_trades", { mine: MINE, theirs: "Trey McBride, Noah Gray" });
s = opensWithSummary(r, "find_trades none");
assert.deepEqual(r.structuredContent.trades, []);
assert.ok(r.structuredContent.closest.length >= 1 && r.structuredContent.closest.length <= 2, JSON.stringify(r.structuredContent));
assert.ok(r.structuredContent.closest.every((t) => !t.viable && t.why.length === t.failed.length && t.why.length > 0));
assert.match(s, /^No trade passes every check; the closest is give .+ for .+ \([+-]\d+\.\d for you\), which fails (one|\d+): /);
assert.match(text(r), /\nClosest \(each fails a check, so they would likely say no\):\n1\. give /);
assert.match(text(r), /\| fails: [a-z]/);
assert.doesNotMatch(text(r), /perceived_fairness|position_protection|their_lineup_improves|\bdepth\b, /);

// ---------- find_trades_league: one answer line, then one notice line per kind (not one per kicker) ----------
r = await call("find_trades_league", { league_teams: league, my_team: "Mine" });
s = opensWithSummary(r, "league");
assert.match(s, /^\d+ trades? the other team would likely accept; best: give .+ to Team 10 for .+ \([+-]\d+\.\d for you\)\.$/);
const lines = text(r).split("\n");
assert.equal(lines.filter((l) => /kicker|defense/.test(l)).length, 1, text(r));
assert.equal(lines.find((l) => /kicker/.test(l)), "Left out: 3 kickers and 3 defenses (not valued).");
assert.ok(lines.indexOf("Left out: 3 kickers and 3 defenses (not valued).") < lines.findIndex((l) => l.startsWith("League scan:")), "notices come before the scan");
// plain words: your gain, the failed checks in words; field names stay
assert.match(text(r), /\| your gain [+-]\d+\.\d \| your lineup /);
assert.doesNotMatch(text(r), /\| edge |perceived_fairness|user_lineup_improves|not viable:/);
const loose = await call("find_trades_league", { league_teams: league, my_team: "Mine", viable_only: false, limit: 100 });
assert.ok(loose.structuredContent.trades.some((t) => t.failed.length) && loose.structuredContent.trades[0].ddfEdge !== undefined);
// a typo and a name that fits two players: one line each
r = await call("find_trades_league", { mine: "Josh Allen, Bijan Robinsn, Rico Runner, Hunter Henry", opponents: [{ name: "Team 10", roster: THEM }, { name: "Team 4", roster: "Henry, Bo Nix" }] });
assert.match(text(r), /^Read as: interpreted "Bijan Robinsn" as Bijan Robinson\.$/m);
assert.match(text(r), /^Could be more than one player: Henry \(Team 4\) could be /m);

// ---------- risers_fallers: owner and a reason for a drop to 0 ----------
r = await call("risers_fallers", { league_teams: league, my_team: "Mine", disagreements: true });
s = opensWithSummary(r, "risers");
assert.match(s, /^Week 10 to 11: biggest riser Free Agent Guy \+6\.0 \(free agent\); biggest faller Bo Nix -18\.0 \(Team 4\)\.$/);
const nix = r.structuredContent.fallers.find((m) => m.name === "Bo Nix");
assert.equal(nix.owner, "Team 4");
assert.equal(nix.reason, "every trade chart has him at 0 this week (often an injury or a role change; check the news); projections 9 -> 9");
assert.match(text(r), /^Bo Nix \(QB, Team 4\): 18\.0 → 0\.0 \(-18\.0\) — every trade chart has him at 0 this week/m);
assert.equal(r.structuredContent.risers.find((m) => m.name === "Free Agent Guy").reason, "4 of 4 trade charts up; projections 3 -> 3");
// the market-vs-projections "buy" carries the reason first
assert.match(text(r), /Bo Nix \(QB, Team 4\): DDF Value -18\.0, projections \+0\.0\. Every trade chart has him at 0 this week .*, so read this first: Panic the projections don't share: buy/);
assert.doesNotMatch(text(r), /injur(ed|y status)|is (out|injured)/, "never an injury claim");
// get_player_value: a 0 who was not 0 last week
r = await call("get_player_value", { names: "Bo Nix" });
assert.match(opensWithSummary(r, "player"), /^Bo Nix \(QB\) is worth 0 DDF Value, tier starter \(was 18 in Week 10; every trade chart has him at 0 this week/);
assert.equal(r.structuredContent.results[0].prior_value, 18);

// ---------- trade_targets: an empty result says what to try; the team's weakest slot ----------
r = await call("trade_targets", { player_name: "Trey McBride", position: "QB", range_pct: 5 });
assert.equal(opensWithSummary(r, "targets empty"), "No QB within 5% of Trey McBride (21). Nearest: Josh Allen (QB) at 30. Try range_pct 45.");
assert.equal(r.structuredContent.nearest.name, "Josh Allen");
r = await call("trade_targets", { player_name: "Hunter Henry", position: "QB" });
assert.equal(r.structuredContent.summary, "No QB within 15% of Hunter Henry (1). Nearest: Bo Nix (QB) at 0. That is more than 50% away, so a 1-for-1 at this value is unlikely.");
r = await call("trade_targets", { player_name: "Trey McBride", position: "WR", range_pct: 1 });
assert.equal(r.structuredContent.summary, "No WR within 1% of Trey McBride (21). Nearest: George Pickens (WR) at 20. Try range_pct 5.");
r = await call("trade_targets", { league_teams: league, my_team: "Mine" });
assert.equal(opensWithSummary(r, "team targets"),
  "Your weakest starter is TE Hunter Henry (1); a typical TE starter here is 9. 4 TEs on other teams would upgrade it; closest: Noah Gray (Team 10, 2).");
assert.deepEqual(r.structuredContent.targets.map((t) => [t.name, t.team]), [["Noah Gray", "Team 10"], ["Dalton Kincaid", "Team 4"], ["Isaiah Likely", "Team 4"], ["Trey McBride", "Team 10"]]);
assert.match((await call("trade_targets", {})).content[0].text, /player_name is required, or give the league/);

// ---------- the state carries the league: a later call needs only the state ----------
r = await call("make_state", { league_teams: league, my_team: "Mine" });
assert.match(opensWithSummary(r, "make_state"), /^Saved 3 teams, yours is Mine with the league settings\./);
const block = codec.encodeBlock(r.structuredContent.state);
r = await call("compare_trade", { state: block, give: "Rico Runner", get: "Trey McBride" });
assert.match(text(r), /^Your starting lineup: \+20\.0 \(TE Hunter Henry 1 -> Trey McBride 21, /m);
r = await call("read_state", { state: block });
assert.match(opensWithSummary(r, "read_state"), /^Read the state: 3 teams \(yours: Mine\), mine \(\d+\)/);

console.log("ok");
