// JEG-1049 / JEG-1256: runs tools/edge_drift_check.mjs against a local fake of the
// deployed mcp and get-values endpoints, so it needs no network. Run by
// tests/test_edge_drift_check.py. Each case pins the exit code: 0 in sync, 1 drift,
// 2 could not compare. EDGE_DRIFT_SCRIPT points it at another copy of the checker
// (used once to show which cases the #1003 version got wrong; see the JEG-1256 log).
// Also unit-tests the pure compareTools() export for field-level drift detection.
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { TOOLS } from "../../supabase/functions/mcp/tools.ts";
import { compareTools } from "../../tools/edge_drift_check.mjs";

const SCRIPT = process.env.EDGE_DRIFT_SCRIPT ||
  fileURLToPath(new URL("../../tools/edge_drift_check.mjs", import.meta.url));
const mainNames = TOOLS.map((t) => t.name);

// A row shaped like main's get-values include=charts (supabase/functions/get-values/index.ts).
const row = (over = {}) => ({
  player_key: 1, name: "A", pos: "WR", value: 50.5, tier: 1,
  chart_values: { fantasycalc: 50, ktc: null }, chart_indexed: { fantasycalc: 48, ktc: null },
  ddf_value_charts: 50.5, ddf_value_projections: 49.1, ...over,
});
const without = (r, ...keys) => Object.fromEntries(Object.entries(r).filter(([k]) => !keys.includes(k)));

const json = (body, status = 200) => ({ status, type: "application/json", body: JSON.stringify(body) });
// toolsWithSchema: build a tools/list reply that includes inputSchema for each tool.
const toolsWithSchemaReply = (tools) =>
  json({ jsonrpc: "2.0", id: 1, result: { tools } });
// Names only drift here: each tool carries main's schema (or an empty one for a tool main lacks).
const toolsReply = (names) =>
  toolsWithSchemaReply(names.map((name) => mainToolsWithSchema.find((t) => t.name === name) ?? { name, inputSchema: { type: "object" } }));
const sse = (payload) => ({ status: 200, type: "text/event-stream", body: `event: message\ndata: ${JSON.stringify(payload)}\n\n` });
const valuesReply = (players) => json({ players, bench_share: { QB: 0.2, overall: 0.3 } });
// Build a tools/list reply that mirrors main's full inputSchema (properties + required).
const mainToolsWithSchema = TOOLS.map((t) => ({
  name: t.name,
  inputSchema: { type: "object", properties: t.inputSchema?.properties ?? {}, required: t.inputSchema?.required ?? [] },
}));
assert.deepEqual(mainToolsWithSchema.find((t) => t.name === "get_player_value")?.inputSchema.required, ["names"],
  "the required-list drift case needs get_player_value to require names on main; point it at a tool that still has required fields");
const OK_MCP = toolsWithSchemaReply(mainToolsWithSchema);
const OK_VALUES = valuesReply([row(), row({ player_key: 2, name: "B" })]);

// initReply for the fake initialize handler.
const initReply = json({ jsonrpc: "2.0", id: 2, result: { protocolVersion: "2025-06-18", serverInfo: { name: "data-driven-football", version: "1.2.0", build: "a".repeat(40) }, capabilities: { tools: {} } } });

function fake({ mcp, values, init = initReply }) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        let reply;
        if (req.url.startsWith("/mcp")) {
          const parsed = JSON.parse(body);
          if (parsed.method === "initialize") {
            reply = init;
          } else {
            assert.equal(parsed.method, "tools/list");
            reply = mcp;
          }
        } else {
          assert.match(req.url, /include=charts/);
          reply = values;
        }
        res.writeHead(reply.status, { "Content-Type": reply.type });
        res.end(reply.body);
      });
    }).listen(0, "127.0.0.1", () => resolve(srv));
  });
}

function runScript(mcpUrl, valuesUrl) {
  return new Promise((resolve) => {
    const p = spawn("node", ["--experimental-strip-types", "--no-warnings", SCRIPT], {
      env: { ...process.env, EDGE_MCP_URL: mcpUrl, EDGE_GET_VALUES_URL: valuesUrl },
    });
    let out = "";
    p.stdout.on("data", (c) => (out += c));
    p.stderr.on("data", (c) => (out += c));
    p.on("close", (code) => resolve({ code, out }));
  });
}

async function scenario({ mcp = OK_MCP, values = OK_VALUES, deadMcp = false, deadValues = false }) {
  const srv = await fake({ mcp, values });
  const base = `http://127.0.0.1:${srv.address().port}`;
  const dead = "http://127.0.0.1:1"; // nothing listens on port 1
  try {
    return await runScript(deadMcp ? `${dead}/mcp` : `${base}/mcp`, deadValues ? `${dead}/get-values` : `${base}/get-values`);
  } finally {
    srv.close();
  }
}

const CASES = [
  // In sync.
  { name: "positive", code: 0, out: /\bOK:/ },
  { name: "positive, mcp answers SSE", mcp: sse({ jsonrpc: "2.0", id: 1, result: { tools: mainToolsWithSchema } }), code: 0, out: /\bOK:/ },
  { name: "legitimate zero is numeric, not unavailable", values: valuesReply([row({ value: 0, ddf_value_charts: 0, ddf_value_projections: 0, chart_values: { fantasycalc: 0 } })]), code: 0, out: /\bOK:/ },
  { name: "null ddf_value_* on some players is allowed (main types it number | null)", values: valuesReply([row({ ddf_value_charts: null, ddf_value_projections: null }), row({ player_key: 2 })]), code: 0, out: /\bOK:/ },
  { name: "no bench_share is not checked (policy held, JEG-1256)", values: json({ players: [row()] }), code: 0, out: /\bOK:/ },

  // Drift.
  { name: "a tool with no inputSchema is unreadable, not drift", mcp: toolsWithSchemaReply(mainToolsWithSchema.map((t, i) => (i ? t : { name: t.name }))),
    code: 2, out: /no inputSchema on / },
  { name: "missing and extra tools", mcp: toolsReply([...mainNames.slice(1), "ghost_tool"]), code: 1,
    out: new RegExp(`not deployed: ${mainNames[0]}\\b[\\s\\S]*not on main: ghost_tool`) },
  { name: "every player lacks the chart fields (older get-values)", values: valuesReply([without(row(), ...["chart_values", "chart_indexed", "ddf_value_charts", "ddf_value_projections"])]),
    code: 1, out: /no player has chart_values[\s\S]*no player has ddf_value_charts[\s\S]*no player has ddf_value_projections/ },
  { name: "every player lacks one required field", values: valuesReply([without(row(), "ddf_value_projections"), without(row({ player_key: 2 }), "ddf_value_projections")]),
    code: 1, out: /no player has ddf_value_projections/ },
  { name: "drift on mcp still wins when get-values is unavailable", mcp: toolsReply(mainNames.slice(1)), values: valuesReply([]),
    code: 1, out: /not deployed[\s\S]*Also could not compare:[\s\S]*players list is empty/ },
  // Field-level drift: deployed tool is missing a field that main has.
  { name: "deployed tool missing a field",
    mcp: toolsWithSchemaReply(mainToolsWithSchema.map((t) =>
      t.name === "make_state"
        ? { ...t, inputSchema: { ...t.inputSchema, properties: without(t.inputSchema.properties, "mine") } }
        : t)),
    code: 1, out: /make_state:[\s\S]*deployed lacks fields mine/ },
  // Field-level drift: deployed tool has an extra field not on main.
  { name: "deployed tool has extra field",
    mcp: toolsWithSchemaReply(mainToolsWithSchema.map((t) =>
      t.name === "get_values"
        ? { ...t, inputSchema: { ...t.inputSchema, properties: { ...t.inputSchema.properties, ghost_param: { type: "string" } } } }
        : t)),
    code: 1, out: /get_values:[\s\S]*deployed has fields not on main: ghost_param/ },
  // Field-level drift: deployed tool's required list differs. get_player_value keeps a required list on main
  // (compare_trade lost its own when it took give/get); the guard below fails loudly if that changes too.
  { name: "deployed tool required list differs",
    mcp: toolsWithSchemaReply(mainToolsWithSchema.map((t) =>
      t.name === "get_player_value"
        ? { ...t, inputSchema: { ...t.inputSchema, required: [] } }
        : t)),
    code: 1, out: /get_player_value:[\s\S]*deployed required misses: names/ },

  // Could not compare (exit 2).
  { name: "empty players", values: valuesReply([]), code: 2, out: /could not compare[\s\S]*players list is empty/ },
  { name: "ddf_value_* null on every player", values: valuesReply([row({ ddf_value_charts: null }), row({ player_key: 2, ddf_value_charts: null })]),
    code: 2, out: /ddf_value_charts is null on all 2 players/ },
  { name: "non-numeric ddf_value_*", values: valuesReply([row({ ddf_value_projections: "49.1" })]), code: 2, out: /non-numeric ddf_value_projections/ },
  { name: "missing value", values: valuesReply([without(row(), "value")]), code: 2, out: /missing or non-numeric value/ },
  { name: "non-numeric value", values: valuesReply([row({ value: "NaN" })]), code: 2, out: /missing or non-numeric value/ },
  { name: "null chart_values", values: valuesReply([row({ chart_values: null })]), code: 2, out: /chart_values that is not an object/ },
  { name: "chart_values with a non-numeric entry", values: valuesReply([row({ chart_values: { fantasycalc: "50" } })]), code: 2, out: /chart_values that is not an object/ },
  { name: "chart_values all null", values: valuesReply([row({ chart_values: { fantasycalc: null, ktc: null } })]), code: 2, out: /chart_values has no numeric value/ },
  { name: "some players lack a required field", values: valuesReply([row(), without(row({ player_key: 2 }), "ddf_value_charts")]),
    code: 2, out: /1 of 2 players lack ddf_value_charts while the rest have it/ },
  { name: "a player row is null", values: valuesReply([row(), null]), code: 2, out: /1 of 2 players are not objects/ },
  { name: "players is not a list", values: json({ players: { a: 1 } }), code: 2, out: /no players list/ },
  { name: "get-values JSON null", values: json(null), code: 2, out: /no players list/ },
  { name: "get-values not JSON", values: { status: 200, type: "text/html", body: "<html>gateway</html>" }, code: 2, out: /reply is not JSON/ },
  { name: "get-values 403", values: json({ msg: "forbidden" }, 403), code: 2, out: /get-values[\s\S]*HTTP 403/ },
  { name: "mcp 403", mcp: json({ msg: "forbidden" }, 403), code: 2, out: /mcp tools\/list[\s\S]*HTTP 403/ },
  { name: "mcp JSON-RPC error", mcp: json({ jsonrpc: "2.0", id: 1, error: { code: -32601, message: "no" } }), code: 2, out: /JSON-RPC error/ },
  { name: "mcp lists no tools", mcp: toolsReply([]), code: 2, out: /lists no tools/ },
  { name: "mcp tool without a name", mcp: json({ jsonrpc: "2.0", id: 1, result: { tools: [...mainNames.map((name) => ({ name })), { title: "x" }] } }),
    code: 2, out: /1 of \d+ tools have no name/ },
  { name: "mcp SSE with no data line", mcp: { status: 200, type: "text/event-stream", body: "event: ping\n\n" }, code: 2, out: /reply is not JSON/ },
  { name: "mcp unreachable", deadMcp: true, code: 2, out: /mcp tools\/list: cannot reach/ },
  { name: "both unreachable", deadMcp: true, deadValues: true, code: 2, out: /cannot reach[\s\S]*cannot reach/ },
];

const failures = [];
for (const c of CASES) {
  const r = await scenario(c);
  const ok = r.code === c.code && c.out.test(r.out) && !/\n\s+at /.test(r.out) &&
    (c.code !== 0 || !/EDGE (DRIFT|CHECK ERROR)/.test(r.out));
  console.log(`${ok ? "pass" : "FAIL"} [exit ${r.code}, want ${c.code}] ${c.name}`);
  if (!ok) failures.push(`${c.name}: exit ${r.code} (want ${c.code})\n${r.out}`);
}
assert.equal(failures.length, 0, `\n${failures.join("\n\n")}`);

// ---------- unit tests for the pure compareTools() export ----------
{
  const tool = (name, props, required = []) => ({
    name,
    properties: new Set(props),
    required: new Set(required),
  });

  // Identical lists: no drift.
  let lines = compareTools(
    [tool("get_values", ["scoring", "teams"]), tool("explain", ["topic"], ["topic"])],
    [tool("get_values", ["scoring", "teams"]), tool("explain", ["topic"], ["topic"])],
  );
  assert.deepEqual(lines, [], "identical lists produce no drift");

  // Missing tool on deployed side.
  lines = compareTools(
    [tool("get_values", []), tool("make_state", [])],
    [tool("get_values", [])],
  );
  assert.ok(lines.some((l) => l.includes("not deployed") && l.includes("make_state")), "missing tool reported: " + lines);

  // Extra tool on deployed side.
  lines = compareTools(
    [tool("get_values", [])],
    [tool("get_values", []), tool("ghost_tool", [])],
  );
  assert.ok(lines.some((l) => l.includes("not on main") && l.includes("ghost_tool")), "extra tool reported: " + lines);

  // Missing field in deployed tool.
  lines = compareTools(
    [tool("make_state", ["scoring", "teams", "league_teams"])],
    [tool("make_state", ["scoring", "teams"])],
  );
  assert.ok(lines.some((l) => /make_state/.test(l) && /deployed lacks fields.*league_teams/.test(l)), "missing field reported: " + lines);

  // Extra field in deployed tool.
  lines = compareTools(
    [tool("get_values", ["scoring"])],
    [tool("get_values", ["scoring", "ghost_param"])],
  );
  assert.ok(lines.some((l) => /get_values/.test(l) && /deployed has fields not on main.*ghost_param/.test(l)), "extra field reported: " + lines);

  // Required list differs.
  lines = compareTools(
    [tool("compare_trade", ["side_a", "side_b"], ["side_a", "side_b"])],
    [tool("compare_trade", ["side_a", "side_b"], ["side_a"])],
  );
  assert.ok(lines.some((l) => /compare_trade/.test(l) && /deployed required misses.*side_b/.test(l)), "required miss reported: " + lines);

  // Required adds on deployed side.
  lines = compareTools(
    [tool("compare_trade", ["side_a", "side_b"], ["side_a"])],
    [tool("compare_trade", ["side_a", "side_b"], ["side_a", "side_b"])],
  );
  assert.ok(lines.some((l) => /compare_trade/.test(l) && /deployed required adds.*side_b/.test(l)), "required add reported: " + lines);

  console.log("pass [compareTools unit tests]");
}

console.log("ok");
