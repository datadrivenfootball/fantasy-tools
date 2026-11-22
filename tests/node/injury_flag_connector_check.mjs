// Injury flags in the connector (Jeremy, 2026-11-22: "It is a flag, not a stopper"). No network: the deployed
// get-values handler runs on the built dist/ (as get_values_handler_check.mjs does), with v2/player-status.js swapped
// for a test copy, and the MCP tools run on its answers (handleRpc -> tools.ts), with app/v2/finder.js.
//
// 1. Parity: get-values/injury.ts gives the same flag as the site (app/next/injury-flag.js through app/v2/waivers.js)
//    on every case, and the same severity map.
// 2. get-values: a flagged player carries `injury`, a healthy one nothing; with flags on, every value, the player
//    order and every other field are identical to a run with no status file. A stale copy flags nobody.
// 3. Tools on the USO 10-29 league (Team 3 is you): find_trades_league, find_trades, compare_trade and trade_targets
//    give the same answer (structured and text) with flags on as with no status file, once the injury fields and the
//    "[Out, ...]" tags and "Injury flag:" lines are taken out; with flags on, those tags and lines are there.
// Usage: node --experimental-strip-types --no-warnings tests/node/injury_flag_connector_check.mjs <dist dir>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const require = createRequire(import.meta.url);
const dist = resolve(process.argv[2] || "dist");
const ROOT = new URL("../../", import.meta.url);
const read = (p) => readFileSync(new URL(p, ROOT), "utf8");

// ---------- 1. parity with the site ----------
globalThis.TradeValueWaivers = require("../../app/v2/waivers.js");
const SITE = require("../../app/next/injury-flag.js");
const G = await import("../../supabase/functions/get-values/injury.ts");
for (const s of ["Out", "IR", "PUP", "Sus", "Doubtful", "Questionable", "O", "q", " D ", "Injured Reserve", "Active", "Inactive", "NA", "DNR", "", null, 7]) {
  const a = SITE.severity(s), b = G.severity(s);
  assert.deepEqual(a && [a.status, a.label, a.level], b && [b.status, b.label, b.level], `severity ${s}`);
}
const now = Date.parse("2026-11-22T14:10:00Z");
const copy = { as_of: "2026-11-22T13:10:00+00:00", by_sleeper_id: {
  1: { team: "SF", pos: "RB", injury_status: "Out", injury_body_part: "Hamstring" },
  2: { team: "LAR", pos: "WR", injury_status: "IR", injury_body_part: "  Ankle - High " },
  3: { team: "KC", pos: "WR", injury_status: "Questionable" },
  4: { team: "KC", pos: "TE", injury_status: null, injury_body_part: "Knee" },
  5: { team: "KC", pos: "QB", injury_status: "NA" },
  6: { team: "JAX", pos: "WR", injury_status: "Doubtful", injury_body_part: "Toe" },
  7: { team: "NE", pos: "QB", injury_status: "Sus" },
} };
const rows = [
  { sleeper_id: "1", team: "SF", pos: "RB" }, { sleeper_id: "1", team: "KC", pos: "RB" }, { sleeper_id: "1", team: "SF", pos: "WR" },
  { sleeper_id: "2", team: "LA", pos: "WR" }, { sleeper_id: "3", team: "KC", pos: "WR" }, { sleeper_id: "4", team: "KC", pos: "TE" },
  { sleeper_id: "5", team: "KC", pos: "QB" }, { sleeper_id: "6", team: "JAC", pos: "WR" }, { sleeper_id: "7", team: "NE", pos: "QB" },
  { sleeper_id: null, team: "SF", pos: "RB" }, { sleeper_id: "99", team: "SF", pos: "RB" }, { sleeper_id: "1", team: "", pos: "RB" },
];
for (const [nowMs, c] of [[now, copy], [now + 7 * 864e5, copy], [now - 7200e3, copy], [now, { ...copy, as_of: null }]]) {
  const fr = globalThis.TradeValueWaivers.statusFreshness(c, nowMs), src = G.injurySource(c, nowMs);
  assert.equal(src.shown, fr.shown, `shown at ${nowMs}`);
  for (const r of rows) {
    const a = SITE.flagOf({ ...r, name: "X" }, fr), b = G.injuryOf(r, c, src);
    assert.deepEqual(a && [a.status, a.label, a.level, a.body], b && [b.status, b.label, b.level, b.body ?? null], JSON.stringify(r));
  }
}
assert.deepEqual(G.parseStatusScript('window.TradeValueStatus = {"as_of":"x","by_sleeper_id":{}};\n'), { as_of: "x", by_sleeper_id: {} });
assert.equal(G.parseStatusScript("garbage"), null);

// ---------- 2. get-values ----------
const island = JSON.parse(readFileSync(join(dist, "index.html"), "utf8").match(/id="players-data"[^>]*>([\s\S]*?)<\/script>/)[1]).players;
const STATUSES = [["Out", "Hamstring"], ["IR", "Knee"], ["Doubtful", null], ["Questionable", "Ankle"]];
// Every other player with a Sleeper id and a team is flagged, in turn.
const keyed = island.filter((p) => p.sleeper_id && p.team).sort((a, b) => a.player_key - b.player_key);
const flaggedCopy = (asOf) => ({ source: "Sleeper", as_of: asOf, by_sleeper_id: Object.fromEntries(keyed.filter((_, i) => i % 2 === 0)
  .map((p, i) => [String(p.sleeper_id), { team: p.team, pos: p.pos, injury_status: STATUSES[i % 4][0], injury_body_part: STATUSES[i % 4][1] }])) });
const wantFlag = new Map(keyed.filter((_, i) => i % 2 === 0).map((p, i) => [p.player_key, STATUSES[i % 4]]));

let statusBody = null;   // null: 404
globalThis.fetch = async (url) => {
  const path = new URL(String(url)).pathname.replace(/^\/fantasy-tools/, "");
  if (path === "/v2/player-status.js") {
    return statusBody === null ? new Response("not found", { status: 404 }) : new Response(statusBody, { status: 200 });
  }
  const file = join(dist, path === "/" || path === "" ? "index.html" : path);
  try { return new Response(readFileSync(file), { status: 200 }); } catch { return new Response("not found", { status: 404 }); }
};
// One handler module per status copy (each caches its bundle for 5 minutes).
let n = 0;
async function handlerWith(body) {
  statusBody = body;
  let handler = null;
  globalThis.Deno = { env: { get: () => undefined }, serve: (h) => { handler = h; } };
  await import(`../../supabase/functions/get-values/index.ts?copy=${n++}`);
  // The bundle (with the status copy) loads on the first request: warm it while this copy is served.
  const res = await handler(new Request("https://fn.test/functions/v1/get-values", { method: "POST",
    headers: { "content-type": "application/json", "x-forwarded-for": `10.1.0.${n}` }, body: JSON.stringify({ scoring: "ppr", teams: 12 }) }));
  assert.equal(res.status, 200);
  return handler;
}
const js = (c) => "window.TradeValueStatus = " + JSON.stringify(c) + ";\n";
const freshAsOf = new Date(Date.now() - 3600e3).toISOString();
const H = { none: await handlerWith(null), flags: await handlerWith(js(flaggedCopy(freshAsOf))),
  stale: await handlerWith(js(flaggedCopy(new Date(Date.now() - 8 * 864e5).toISOString()))) };
let ip = 0;
const ask = async (h, scoring, teams, superflex, league, week, include) => {
  const res = await h(new Request("https://fn.test/functions/v1/get-values", { method: "POST",
    headers: { "content-type": "application/json", "x-forwarded-for": `10.0.0.${ip++ % 250}` },
    body: JSON.stringify({ scoring, teams, superflex, ...(league ? { league } : {}), ...(week ? { week } : {}), ...(include ? { include } : {}) }) }));
  assert.equal(res.status, 200, `get-values ${res.status}`);
  return res.json();
};
const strip = (body) => JSON.parse(JSON.stringify(body, (k, v) => (k === "injury" || k === "injury_source" ? undefined : v)));
for (const include of [undefined, "charts"]) {
  const none = await ask(H.none, "half_ppr", 12, 0, null, null, include), on = await ask(H.flags, "half_ppr", 12, 0, null, null, include);
  const stale = await ask(H.stale, "half_ppr", 12, 0, null, null, include);
  assert.ok(none.players.length > 100);
  assert.deepEqual(strip(on), strip(none), `include=${include}: flags changed the answer`);
  assert.ok(none.players.every((p) => !p.injury) && stale.players.every((p) => !p.injury), "a missing or stale copy flags nobody");
  assert.equal(none.injury_source.shown, false);
  assert.equal(stale.injury_source.shown, false);
  assert.equal(on.injury_source.shown, true);
  let flagged = 0;
  for (const p of on.players) {
    const want = wantFlag.get(p.player_key);
    if (!want) { assert.equal(p.injury, undefined, `${p.name} is healthy`); continue; }
    flagged += 1;
    assert.equal(p.injury.status, want[0], p.name);
    assert.equal(p.injury.body, want[1] ? want[1].toLowerCase() : undefined, p.name);
  }
  assert.ok(flagged > 50, `only ${flagged} priced players flagged`);
}

// ---------- 3. the tools on the USO league ----------
const { handleRpc } = await import("../../supabase/functions/mcp/rpc.ts");
const finder = require("../../app/v2/finder.js");
const deps = { codec: require("../../app/v2/ddf-state.js"), siteOrigin: "https://site.test" };
const uso = JSON.parse(read("tests/fixtures/league_levels/uso.json")).league.teams;
const me = uso.find((t) => t.id === "3");
const names = (t) => t.players.filter((p) => p.key).map((p) => p.name);
const leagueTeams = uso.map((t) => ({ name: `Team ${t.id}`, roster: names(t).join("\n") }));
const LEAGUE_ROSTER = { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 5 };
async function tool(h, name, args) {
  const values = (s, t, sf, league, week) => ask(h, s, t, sf, league, week);
  const charts = (s, t, sf, league, week) => ask(h, s, t, sf, league, week, "charts");
  const r = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: {
    scoring: "half_ppr", teams: 12, superflex: false, ...args } } }, values, deps, { finder, fetchCharts: charts });
  assert.ok(!r.error && !r.result.isError, `${name}: ${JSON.stringify(r.error ?? r.result.content).slice(0, 400)}`);
  return r.result;
}
const TAG = / \[(Out|IR|PUP|Suspended|Doubtful|Questionable)(, [^\]]+)?\]/g;
const textOf = (r) => r.content.map((c) => c.text).join("\n");
const plainText = (t) => t.split("\n").filter((l) => !/^\s*Injury flag: /.test(l)).join("\n").replace(TAG, "");
const theirs = uso.find((t) => t.id === "9");
const calls = [
  ["find_trades_league", { league_teams: leagueTeams, my_team: "Team 3", roster: LEAGUE_ROSTER, viable_only: false, limit: 20 }],
  ["find_trades", { mine: names(me).join("\n"), theirs: names(theirs).join("\n"), viable_only: false, limit: 20 }],
  ["compare_trade", { give: "Christian McCaffrey, Denzel Boston", get: "James Cook III, Derrick Henry" }],
  ["trade_targets", { player_name: "Drake Maye", range_pct: 25 }],
];
let tagged = 0;
for (const [name, args] of calls) {
  const none = await tool(H.none, name, args), on = await tool(H.flags, name, args);
  assert.deepEqual(strip(on.structuredContent), strip(none.structuredContent), `${name}: flags changed the structured answer`);
  assert.equal(plainText(textOf(on)), textOf(none), `${name}: flags changed the text beyond the tags and flag lines`);
  assert.doesNotMatch(textOf(none), /Injury flag:|\[(Out|IR|Questionable|Doubtful)/, `${name}: a flag with no status copy`);
  const tags = textOf(on).match(TAG) || [];
  const lines = textOf(on).split("\n").filter((l) => /^\s*Injury flag: /.test(l));
  assert.ok(tags.length > 0 && lines.length > 0, `${name}: no injury tag or line with half the players flagged`);
  assert.ok(lines.every((l) => /\. A flag, not a stopper: the trade may not work as planned\.$/.test(l)), `${name}: ${lines[0]}`);
  tagged += tags.length;
}
// A flagged player's line names the status and body part the copy gave (Out, hamstring -> "is Out (hamstring)").
const cmc = keyed.find((p) => p.name === "Christian McCaffrey");
if (cmc && wantFlag.has(cmc.player_key)) {
  const [s, body] = wantFlag.get(cmc.player_key);
  const out = textOf(await tool(H.flags, "compare_trade", calls[2][1]));
  const phrase = (s === "IR" ? "on IR" : s) + (body ? ` (${body.toLowerCase()})` : "");
  assert.match(out, new RegExp(`Christian McCaffrey is ${phrase.replace(/[()]/g, "\\$&")}`));
}
console.log(`injury flags: ${tagged} tags across ${calls.length} tools, answers unchanged otherwise`);
console.log("ok");
