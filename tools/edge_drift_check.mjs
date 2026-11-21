// JEG-1049: drift check for the manually deployed Supabase edge functions.
// Compares the deployed `mcp` tools/list with the TOOLS declared on main
// (supabase/functions/mcp/tools.ts) and checks that deployed `get-values`
// answers include=charts with the shape the find_trades finder reads.
// Also compares top-level inputSchema.properties keys and required lists for
// each tool, and reads the deployed server's initialize build SHA.
// Read-only, no secrets, never deploys.
//
// Exit codes (JEG-1256):
//   0  in sync: both sides were read and match main.
//   1  drift: a side was read and differs from main (tool names, input fields,
//      or every player lacks a chart field main returns). Proven drift wins
//      over an unavailable side.
//   2  could not compare: an endpoint was unreachable, answered non-2xx or
//      something unreadable, or its evidence was empty, inconsistent or
//      non-numeric. Never reported as healthy, never reported as drift.
//
// Run: node --experimental-strip-types --no-warnings tools/edge_drift_check.mjs
// Env: EDGE_MCP_URL, EDGE_GET_VALUES_URL override the production endpoints.
import { fileURLToPath } from "node:url";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const BASE = "https://iskiybsimubiujwuchsl.supabase.co/functions/v1";
const MCP_URL = process.env.EDGE_MCP_URL || `${BASE}/mcp`;
const VALUES_URL = process.env.EDGE_GET_VALUES_URL || `${BASE}/get-values`;
const TIMEOUT_MS = 60_000; // get-values is slow on a cold start

// Fields main's get-values adds under include=charts (supabase/functions/get-values/index.ts).
// All three are on every row, so a deploy either returns them on every player or on none.
const CHART_FIELDS = ["chart_values", "ddf_value_charts", "ddf_value_projections"];
// Main types these as number | null (mcp/tools.ts); null on one player is legitimate.
const NULLABLE_NUMBERS = ["ddf_value_charts", "ddf_value_projections"];
// Fields every get-values build returns as numbers (rows without a finite value are skipped).
const REQUIRED_NUMBERS = ["player_key", "value"];

class Unavailable extends Error {}

const isNumber = (v) => typeof v === "number" && Number.isFinite(v);
const isPlainObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

async function request(label, url, init) {
  let res;
  try {
    res = await fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (e) {
    throw new Unavailable(`${label}: cannot reach ${url} (${e.cause?.code || e.message})`);
  }
  let text;
  try {
    text = await res.text();
  } catch (e) {
    throw new Unavailable(`${label}: ${url} reply was cut off (${e.cause?.code || e.message})`);
  }
  if (!res.ok) throw new Unavailable(`${label}: ${url} answered HTTP ${res.status}: ${text.slice(0, 200)}`);
  return text;
}

// The mcp function is stateless (no initialize needed) and answers plain JSON, but a
// Streamable HTTP server may legally answer with SSE, so accept `data:` lines too.
function parseReply(label, text) {
  const body = text.trimStart().startsWith("{")
    ? text
    : text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
  try {
    return JSON.parse(body);
  } catch {
    throw new Unavailable(`${label}: reply is not JSON: ${text.slice(0, 200)}`);
  }
}

// Send an initialize request and return { version, build } from serverInfo.
// A failure to read build is noted but not an error.
async function deployedServerInfo() {
  const label = "mcp initialize";
  let text;
  try {
    text = await request(label, MCP_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "initialize", params: { protocolVersion: "2025-06-18" } }),
    });
  } catch (e) {
    // Not fatal: initialize failure is a note, not exit 2.
    return { note: e.message };
  }
  let reply;
  try {
    reply = parseReply(label, text);
  } catch (e) {
    return { note: e.message };
  }
  const info = reply?.result?.serverInfo;
  if (!isPlainObject(info)) return { note: "initialize: no serverInfo in reply" };
  return {
    version: typeof info.version === "string" ? info.version : undefined,
    build: typeof info.build === "string" ? info.build : undefined,
  };
}

// Return { tools: [{name, properties: Set, required: Set}] } from the deployed server.
// Throws Unavailable when the reply can't serve as evidence.
async function deployedToolsData() {
  const text = await request("mcp tools/list", MCP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }),
  });
  const reply = parseReply("mcp tools/list", text);
  if (reply?.error) {
    throw new Unavailable(`mcp tools/list: JSON-RPC error: ${JSON.stringify(reply.error).slice(0, 200)}`);
  }
  const tools = reply?.result?.tools;
  if (!Array.isArray(tools)) {
    throw new Unavailable(`mcp tools/list: no result.tools in reply: ${JSON.stringify(reply).slice(0, 200)}`);
  }
  if (tools.length === 0) throw new Unavailable("mcp tools/list: reply lists no tools");
  const unnamed = tools.filter((t) => !isPlainObject(t) || typeof t.name !== "string" || t.name === "");
  if (unnamed.length) {
    throw new Unavailable(`mcp tools/list: ${unnamed.length} of ${tools.length} tools have no name`);
  }
  return tools.map((t) => ({
    name: t.name,
    properties: new Set(isPlainObject(t.inputSchema?.properties) ? Object.keys(t.inputSchema.properties) : []),
    required: new Set(Array.isArray(t.inputSchema?.required) ? t.inputSchema.required : []),
  }));
}

// Pure function: compare main tools vs deployed tools, returning drift message lines.
// mainTools and deployedTools each have { name, properties: Set, required: Set }.
// Exported so tests can call it without network.
export function compareTools(mainTools, deployedTools) {
  const drift = [];
  const mainByName = new Map(mainTools.map((t) => [t.name, t]));
  const deployedByName = new Map(deployedTools.map((t) => [t.name, t]));

  const missingTools = mainTools.filter((t) => !deployedByName.has(t.name)).map((t) => t.name);
  const extraTools = deployedTools.filter((t) => !mainByName.has(t.name)).map((t) => t.name);
  if (missingTools.length) drift.push(`mcp tools on main but not deployed: ${missingTools.join(", ")}`);
  if (extraTools.length) drift.push(`mcp tools deployed but not on main: ${extraTools.join(", ")}`);

  // For tools present on both sides, compare inputSchema.properties and required.
  for (const [name, mainTool] of mainByName) {
    const dep = deployedByName.get(name);
    if (!dep) continue; // already reported above
    const missingFields = [...mainTool.properties].filter((f) => !dep.properties.has(f));
    const extraFields = [...dep.properties].filter((f) => !mainTool.properties.has(f));
    const missingRequired = [...mainTool.required].filter((r) => !dep.required.has(r));
    const extraRequired = [...dep.required].filter((r) => !mainTool.required.has(r));
    const parts = [];
    if (missingFields.length) parts.push(`deployed lacks fields ${missingFields.join(", ")}`);
    if (extraFields.length) parts.push(`deployed has fields not on main: ${extraFields.join(", ")}`);
    if (missingRequired.length) parts.push(`deployed required misses: ${missingRequired.join(", ")}`);
    if (extraRequired.length) parts.push(`deployed required adds: ${extraRequired.join(", ")}`);
    if (parts.length) drift.push(`${name}: ${parts.join("; ")}`);
  }
  return drift;
}

// Returns drift messages; throws Unavailable when the reply can't serve as evidence.
async function valuesDrift() {
  const url = new URL(VALUES_URL);
  url.searchParams.set("scoring", "ppr");
  url.searchParams.set("teams", "12");
  url.searchParams.set("superflex", "0");
  url.searchParams.set("include", "charts");
  const label = "get-values include=charts";
  const text = await request(label, url, { headers: { Accept: "application/json" } });
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Unavailable(`${label}: reply is not JSON: ${text.slice(0, 200)}`);
  }
  if (!isPlainObject(data) || !Array.isArray(data.players)) {
    throw new Unavailable(`${label}: reply has no players list: ${text.slice(0, 200)}`);
  }
  const players = data.players;
  const n = players.length;
  if (n === 0) throw new Unavailable(`${label}: players list is empty`);
  const notRows = players.filter((p) => !isPlainObject(p)).length;
  if (notRows) throw new Unavailable(`${label}: ${notRows} of ${n} players are not objects`);

  const unreadable = [];
  for (const f of REQUIRED_NUMBERS) {
    const bad = players.filter((p) => !isNumber(p[f])).length;
    if (bad) unreadable.push(`${bad} of ${n} players have a missing or non-numeric ${f}`);
  }

  const drift = [];
  for (const f of CHART_FIELDS) {
    const lacking = players.filter((p) => !(f in p)).length;
    if (lacking === n) {
      drift.push(`${label}: no player has ${f} (deployed get-values is older than main)`);
      continue;
    }
    if (lacking) {
      // Main writes these on every row, so a partial set fits no deploy: unreadable, not drift.
      unreadable.push(`${lacking} of ${n} players lack ${f} while the rest have it`);
      continue;
    }
    if (f === "chart_values") {
      const bad = players.filter((p) => !isPlainObject(p.chart_values) ||
        Object.values(p.chart_values).some((v) => v !== null && !isNumber(v))).length;
      if (bad) unreadable.push(`${bad} of ${n} players have chart_values that is not an object of numbers or nulls`);
      else if (players.every((p) => Object.values(p.chart_values).every((v) => v === null))) {
        unreadable.push(`chart_values has no numeric value on any of ${n} players`);
      }
    } else if (NULLABLE_NUMBERS.includes(f)) {
      const bad = players.filter((p) => p[f] !== null && !isNumber(p[f])).length;
      if (bad) unreadable.push(`${bad} of ${n} players have a non-numeric ${f}`);
      else if (players.every((p) => p[f] === null)) unreadable.push(`${f} is null on all ${n} players`);
    }
  }
  if (unreadable.length) throw new Unavailable(`${label}: ${unreadable.join("; ")}`);
  return drift;
}

async function mainToolsData() {
  try {
    const { TOOLS } = await import(fileURLToPath(new URL("../supabase/functions/mcp/tools.ts", import.meta.url)));
    return TOOLS.map((t) => ({
      name: t.name,
      properties: new Set(isPlainObject(t.inputSchema?.properties) ? Object.keys(t.inputSchema.properties) : []),
      required: new Set(Array.isArray(t.inputSchema?.required) ? t.inputSchema.required : []),
    }));
  } catch (e) {
    throw new Unavailable(`main: cannot read TOOLS from supabase/functions/mcp/tools.ts (${e.message})`);
  }
}

// Try to determine whether the deployed build SHA is an ancestor of HEAD
// (meaning the deployed code is at or behind the checked-out main).
// Returns a string note; never throws.
async function ancestryNote(buildSha) {
  if (!buildSha || !/^[0-9a-f]{40}$/i.test(buildSha)) return "build not compared (no valid SHA)";
  try {
    // Check whether the last commit touching supabase/functions/mcp/ is an ancestor of the build SHA.
    const { stdout: logOut } = await execFileAsync(
      "git", ["log", "--oneline", "-1", "--", "supabase/functions/mcp/"],
      { cwd: fileURLToPath(new URL("..", import.meta.url)) }
    );
    const mcpHead = logOut.trim().split(" ")[0];
    if (!mcpHead) return "build not compared (no commits found for supabase/functions/mcp/)";
    const { code } = await new Promise((resolve) => {
      const { spawn } = require("node:child_process");
      const p = spawn("git", ["merge-base", "--is-ancestor", mcpHead, buildSha], {
        cwd: fileURLToPath(new URL("..", import.meta.url)),
      });
      p.on("close", (code) => resolve({ code }));
    });
    if (code === 0) return `build ${buildSha.slice(0, 9)} contains last mcp commit ${mcpHead}`;
    if (code === 1) return `build ${buildSha.slice(0, 9)} does NOT contain last mcp commit ${mcpHead} — redeploy needed`;
    return "build not compared (git merge-base returned unexpected code)";
  } catch (e) {
    return `build not compared (${e.message})`;
  }
}

// Any failure while reading a side, expected or not, means that side could not be compared.
const reason = (e) => (e instanceof Unavailable ? e.message : `unexpected error: ${e?.message || e}`);

export async function main() {
  const onMain = await mainToolsData();
  const [deployedResult, values, serverInfoResult] = await Promise.allSettled([
    deployedToolsData(),
    valuesDrift(),
    deployedServerInfo(),
  ]);
  const drift = [];
  const unavailable = [];
  let deployed = null;

  if (deployedResult.status === "fulfilled") {
    deployed = deployedResult.value;
    drift.push(...compareTools(onMain, deployed));
  } else {
    unavailable.push(reason(deployedResult.reason));
  }

  if (values.status === "fulfilled") drift.push(...values.value);
  else unavailable.push(reason(values.reason));

  // Print server info (version + build); note ancestry if build SHA is present.
  const serverInfo = serverInfoResult.status === "fulfilled" ? serverInfoResult.value : {};
  if (serverInfo.version || serverInfo.build) {
    console.log(`deployed mcp: version=${serverInfo.version ?? "unknown"} build=${serverInfo.build ?? "unknown"}`);
  }
  if (serverInfo.note) {
    console.log(`note: ${serverInfo.note}`);
  }
  if (serverInfo.build) {
    // Use dynamic import of child_process for the ancestry check (gracefully skip if unavailable).
    try {
      const { execFile: ef } = await import("node:child_process");
      const { promisify: p } = await import("node:util");
      const efa = p(ef);
      const root = fileURLToPath(new URL("..", import.meta.url));
      const { stdout: logOut } = await efa("git", ["log", "--oneline", "-1", "--", "supabase/functions/mcp/"], { cwd: root });
      const mcpHead = logOut.trim().split(" ")[0];
      if (mcpHead) {
        // git merge-base --is-ancestor exits 0 if ancestor, 1 if not, 128 if unknown
        const code = await new Promise((resolve) => {
          import("node:child_process").then(({ spawn }) => {
            const cp = spawn("git", ["merge-base", "--is-ancestor", mcpHead, serverInfo.build], { cwd: root });
            cp.on("close", resolve);
          }).catch(() => resolve(128));
        });
        if (code === 0) {
          console.log(`ancestry: build ${serverInfo.build.slice(0, 9)} contains last mcp commit ${mcpHead} (up to date)`);
        } else if (code === 1) {
          console.log(`ancestry: build ${serverInfo.build.slice(0, 9)} does NOT contain last mcp commit ${mcpHead} — redeploy may be needed`);
        } else {
          console.log("build not compared (git merge-base returned unexpected code or SHA unknown)");
        }
      } else {
        console.log("build not compared (no commits found for supabase/functions/mcp/)");
      }
    } catch {
      console.log("build not compared (git not available)");
    }
  }

  if (drift.length) {
    console.error(`EDGE DRIFT: deployed functions are out of step with main (deploys are manual):\n- ${drift.join("\n- ")}`);
    if (deployed) console.error(`mcp on main: ${onMain.length} tools; deployed: ${deployed.length} tools.`);
    if (unavailable.length) console.error(`Also could not compare:\n- ${unavailable.join("\n- ")}`);
    process.exit(1);
  }
  if (unavailable.length) {
    console.error(`EDGE CHECK ERROR (could not compare): this is not a healthy result and not a drift verdict.\n- ${unavailable.join("\n- ")}`);
    process.exit(2);
  }
  console.log(`OK: deployed mcp lists the same ${onMain.length} tools as main with matching input fields; get-values include=charts has the chart fields.`);
}

// Guard so importing (e.g. from tests) does not run main().
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((e) => {
    console.error(`EDGE CHECK ERROR (could not compare): ${reason(e)}`);
    process.exit(2);
  });
}
