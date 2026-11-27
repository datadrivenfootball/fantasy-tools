// JEG-1543 phase 2: get-answers, the answers version's recommendations endpoint (Supabase edge function).
//
// POST {league, me:{keys, index?, others?}, opponents:[{id, name, keys}], skipped?, sizes?, held?, ov?, min_bench?}
// -> Trade & Waiver Recommendations computed as the full site's find.html computes them (core.ts), with no source data
// in the reply: player keys, DDF numbers and words only, checked against an explicit allowlist before it is sent.
// Requests for source-level output (include, basis, per-source fields) are refused. Sizes 1-2 only (CPU cap).
//
// Loads, like get-values: value-model.js, the source bundle and the players-data island from the published site
// (server memory only, never in a reply), plus the page modules find.html runs (core.ts PAGE_SCRIPTS).
// No accounts, no keys, no storage. Deploy: docs/get-answers-deploy.md (needs Jeremy's yes; the lead deploys).

const SITE_ORIGIN = (Deno.env.get("DDF_SITE_ORIGIN") ||
  "https://jb-barrel-droid.github.io/fantasy-tools").replace(/\/+$/, "");
const BUNDLE_URL = `${SITE_ORIGIN}/assets/comparison-sources-data.json`;
const PAGE_URL = `${SITE_ORIGIN}/`;
const VALUE_MODEL_URL = `${SITE_ORIGIN}/assets/value-model.js`;
const LINEUP_PARAMS_URL = `${SITE_ORIGIN}/assets/lineup-parameters.json`;
const HISTORY_INDEX_URL = `${SITE_ORIGIN}/assets/history/index.json`;

import { answer, compileScripts, type CompiledScript, PAGE_SCRIPTS, parseRequest } from "./core.ts";
import { todayIso } from "../get-values/pipeline.ts";

// deno-lint-ignore no-explicit-any
type Any = any;

interface Loaded {
  bundle: Any;
  valueLink: Any;
  scripts: CompiledScript[];
  runs: Map<string, Any>;
  loadedAt: number;
}

let cached: Loaded | null = null;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes, as get-values
const RUNS_MAX = 6;

async function text(url: string): Promise<string> {
  const res = await fetch(url);
  // The message never names the file: an error reply must not carry a source file's name either.
  if (!res.ok) throw new Error(`a site file did not load (${res.status})`);
  return await res.text();
}

// One saved week's document (assets/history/week-<N>.json), as get-values loads it.
async function loadHistoryDoc(bundle: Any, week: number): Promise<void> {
  const history = bundle.history;
  if (!history || history.docs[String(week)]) return;
  const file = history.index?.weeks?.[String(week)]?.file;
  if (typeof file !== "string" || !/^[\w./-]+\.json$/.test(file) || file.includes("..")) return;
  try {
    const res = await fetch(`${SITE_ORIGIN}/${file.replace(/^\/+/, "")}`);
    if (!res.ok) return;
    const doc = await res.json();
    if (doc?.week === week) history.docs[String(week)] = doc;
  } catch {
    // Left unloaded: the sources that needed it are left out for this week, as in get-values.
  }
}

async function load(): Promise<Loaded> {
  if (cached && Date.now() - cached.loadedAt < CACHE_TTL_MS) return cached;
  const [vmSource, detailText, html, lpText, historyText, ...pageSources] = await Promise.all([
    text(VALUE_MODEL_URL), text(BUNDLE_URL), text(PAGE_URL),
    text(LINEUP_PARAMS_URL).catch(() => null), text(HISTORY_INDEX_URL).catch(() => null),
    ...PAGE_SCRIPTS.map((p) => text(`${SITE_ORIGIN}/${p}`)),
  ]);
  // value-model.js publishes ValueModel on the global (as in get-values).
  // deno-lint-ignore no-eval
  const evalFn = eval;
  evalFn(vmSource);
  const ValueModel = (globalThis as Any).ValueModel;
  if (!ValueModel || typeof ValueModel.runValuePipeline !== "function") throw new Error("ValueModel.runValuePipeline not found");
  const match = html.match(/id="players-data"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) throw new Error("players-data island not found in page");
  const playersDoc = JSON.parse(match[1]);
  let lineupConfig = null;
  try { lineupConfig = lpText ? JSON.parse(lpText) : null; } catch { lineupConfig = null; }
  let history = null;
  try { history = historyText ? { index: JSON.parse(historyText), docs: {} } : null; } catch { history = null; }
  const sources = Object.fromEntries(PAGE_SCRIPTS.map((p, i) => [p, pageSources[i] as string]));
  const scripts = compileScripts(sources);
  // The site's share-link reader, for ov= (the same file get-values evaluates).
  evalFn(sources["v2/ddf-value-link.js"]);
  const valueLink = (globalThis as Any).DDFValueLink ?? null;
  cached = {
    bundle: { detail: JSON.parse(detailText), players: playersDoc.players, meta: playersDoc.meta, ValueModel, lineupConfig, history },
    valueLink, scripts, runs: new Map(), loadedAt: Date.now(),
  };
  return cached;
}

// --- CORS (get-values' allowed origins) ---------------------------------------------------------------------------
const ALLOWED_ORIGINS = new Set([
  "https://datadrivenfootball.com",
  "https://datadrivenfootball.github.io",
  "https://jb-barrel-droid.github.io",
  "http://localhost:3000",
  "http://localhost:5173",
  "http://127.0.0.1:3000",
  "http://127.0.0.1:5173",
]);

function corsHeaders(req: Request): Record<string, string> {
  const origin = req.headers.get("origin") || "";
  const headers: Record<string, string> = {
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
  if (ALLOWED_ORIGINS.has(origin)) headers["Access-Control-Allow-Origin"] = origin;
  return headers;
}

// --- Rate limiting: get-values' soft per-IP guard (JEG-1061: per instance, client-forgeable key; it only blunts a
// naive burst against one warm instance, never a guarantee). Every answer is an engine run, so one budget. ------------
const rateBuckets = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 30; // requests per window
const RATE_WINDOW_MS = 60_000; // 1 minute
const MAX_BODY = 64 * 1024;

function checkRate(ip: string): boolean {
  const now = Date.now();
  let bucket = rateBuckets.get(ip);
  if (!bucket || now >= bucket.resetAt) {
    bucket = { count: 0, resetAt: now + RATE_WINDOW_MS };
    rateBuckets.set(ip, bucket);
  }
  bucket.count++;
  return bucket.count <= RATE_LIMIT;
}

// One structured line per answer and per 429 (get-values' style): settings and counts only, no IP, header or player.
function logEvent(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

Deno.serve(async (req: Request) => {
  const cors = corsHeaders(req);
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || req.headers.get("cf-connecting-ip") || "unknown";
  if (!checkRate(ip)) {
    logEvent({ event: "get_answers.rate_limited", max: RATE_LIMIT, window_s: RATE_WINDOW_MS / 1000 });
    return Response.json({ error: "rate limited", retry_after_seconds: 60 }, { status: 429, headers: cors });
  }
  if (req.method !== "POST") return Response.json({ error: "POST only", code: "method" }, { status: 405, headers: cors });
  try {
    const raw = await req.text();
    if (raw.length > MAX_BODY) return Response.json({ error: "request too large", code: "too_large" }, { status: 413, headers: cors });
    let body: unknown;
    try { body = JSON.parse(raw); } catch { return Response.json({ error: "the body must be JSON", code: "bad_request" }, { status: 400, headers: cors }); }
    const parsed = parseRequest(body);
    if (!parsed.ok) {
      return Response.json({ error: parsed.refusal.error, code: parsed.refusal.code }, { status: parsed.refusal.status, headers: cors });
    }
    const loaded = await load();
    if (loaded.runs.size >= RUNS_MAX) loaded.runs.delete(loaded.runs.keys().next().value as string);
    const started = performance.now();
    const out = await answer(parsed.req, {
      bundle: loaded.bundle, valueLink: loaded.valueLink, scripts: loaded.scripts, runs: loaded.runs,
      today: Deno.env.get("DDF_TODAY") || todayIso(), loadHistoryDoc: (week) => loadHistoryDoc(loaded.bundle, week),
    });
    const b = out.body;
    logEvent({ event: "get_answers.compute", status: out.status, scoring: b?.setting?.scoring ?? null, teams: b?.setting?.teams ?? null,
      superflex: b?.setting?.superflex ?? null, partners: b?.notes?.searched?.length ?? null, sizes: parsed.req.sizes,
      overrides: b?.notes?.overrides ?? null, ms: Math.round(performance.now() - started) });
    return Response.json(out.body, { status: out.status, headers: { ...cors, "Cache-Control": "no-store" } });
  } catch (e) {
    console.error("get-answers error:", e);
    return Response.json({ error: "internal error", message: String((e as Error).message) }, { status: 500, headers: cors });
  }
});
