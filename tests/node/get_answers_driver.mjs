// JEG-1543 phase 2: runs the get-answers edge function in node for tests/test_get_answers.py.
//
// Default mode runs the deployed handler itself (supabase/functions/get-answers/index.ts) with a stub Deno and a fetch
// that serves the built dist/ (the get_values_handler_check.mjs pattern), so the wiring, CORS, refusals and the reply
// allowlist all run as deployed. --raw calls core.ts answer() with the allowlist off (the broken-variant test reads what
// a leaking build would have sent). --functions <dir> loads the function from another copy (the broken variant).
//
// Usage: node --experimental-strip-types tests/node/get_answers_driver.mjs <dist> <requests.json> [--raw] [--functions <dir>]
//   requests.json: [{body, ip?, method?, origin?}]  ->  stdout: [{status, headers:{...}, body, cpu_ms, wall_ms}]
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const dist = resolve(args[0] || "dist");
const requests = JSON.parse(readFileSync(args[1], "utf8"));
const raw = args.includes("--raw");
const fnAt = args.indexOf("--functions");
const functions = resolve(fnAt >= 0 ? args[fnAt + 1] : "supabase/functions");

const serveFile = (path) => {
  const file = join(dist, path === "/" || path === "" ? "index.html" : path);
  return readFileSync(file);
};
globalThis.fetch = async (url) => {
  const path = new URL(String(url)).pathname.replace(/^\/fantasy-tools/, "");
  try { return new Response(serveFile(path), { status: 200 }); } catch { return new Response("not found", { status: 404 }); }
};
const env = { DDF_TODAY: process.env.DDF_TODAY };
let handler = null;
globalThis.Deno = { env: { get: (k) => env[k] }, serve: (h) => { handler = h; } };
const quiet = console.log;
const logs = [];
console.log = (...a) => logs.push(a.join(" "));

const timed = async (fn) => {
  const c0 = process.cpuUsage(), t0 = performance.now();
  const out = await fn();
  const c = process.cpuUsage(c0);
  return { ...out, cpu_ms: Math.round((c.user + c.system) / 1000), wall_ms: Math.round(performance.now() - t0) };
};

const results = [];
if (raw) {
  const core = await import(pathToFileURL(join(functions, "get-answers/core.ts")).href);
  const { todayIso } = await import(pathToFileURL(join(functions, "get-values/pipeline.ts")).href);
  // The same inputs index.ts load() reads from the site, read from dist/.
  const { createRequire } = await import("node:module");
  const require = createRequire(import.meta.url);
  const ValueModel = require(join(dist, "assets/value-model.js"));
  const html = serveFile("/index.html").toString("utf8");
  const playersDoc = JSON.parse(html.match(/id="players-data"[^>]*>([\s\S]*?)<\/script>/)[1]);
  const read = (p) => JSON.parse(serveFile(p).toString("utf8"));
  const history = { index: read("/assets/history/index.json"), docs: {} };
  const sources = Object.fromEntries(core.PAGE_SCRIPTS.map((p) => [p, serveFile("/" + p).toString("utf8")]));
  const valueLink = require(join(dist, "v2/ddf-value-link.js"));
  const deps = {
    bundle: { detail: read("/assets/comparison-sources-data.json"), players: playersDoc.players, meta: playersDoc.meta, ValueModel,
      lineupConfig: read("/assets/lineup-parameters.json"), history },
    valueLink, scripts: core.compileScripts(sources), runs: new Map(), today: env.DDF_TODAY || todayIso(),
    loadHistoryDoc: async (week) => {
      const file = history.index?.weeks?.[String(week)]?.file;
      if (!file || history.docs[String(week)]) return;
      try { const doc = read("/" + file); if (doc.week === week) history.docs[String(week)] = doc; } catch { /* left unloaded */ }
    },
  };
  for (const r of requests) {
    const parsed = core.parseRequest(r.body);
    if (!parsed.ok) { results.push({ status: parsed.refusal.status, body: { error: parsed.refusal.error, code: parsed.refusal.code } }); continue; }
    results.push(await timed(() => core.answer(parsed.req, deps, { validate: false })));
  }
} else {
  await import(pathToFileURL(join(functions, "get-answers/index.ts")).href);
  if (typeof handler !== "function") throw new Error("index.ts did not register a Deno.serve handler");
  for (const r of requests) {
    const headers = { "content-type": "application/json", "x-forwarded-for": r.ip || "10.0.0.1" };
    if (r.origin) headers.origin = r.origin;
    const init = { method: r.method || "POST", headers };
    if (init.method === "POST") init.body = typeof r.body === "string" ? r.body : JSON.stringify(r.body);
    results.push(await timed(async () => {
      const res = await handler(new Request("https://fn.test/functions/v1/get-answers", init));
      const text = await res.text();
      return { status: res.status, headers: Object.fromEntries(res.headers.entries()), text, body: text ? JSON.parse(text) : null };
    }));
  }
}
console.log = quiet;
process.stdout.write(JSON.stringify({ results, logs }));
