// Draft tool daily pull (JEG-1667, Phase 0). NOT DEPLOYED: deploy only on
// Jeremy's named yes (AGENTS.md: every edge-function deploy).
//
// Pulls the recurring draft data that is the same for every league and saves
// it to public.draft_market_values with its pull date; every attempt is
// logged in public.draft_pulls. League-specific math runs client side
// (app/draft/draft-engine.js).
//   - FantasyPros 2026 draft ECR, Standard / Half PPR / PPR (public cheat
//     sheet pages, 6 s apart for the 5 s crawl delay).
//   - ESPN 2026 published auction values, average auction value and ADP.
//
// At most one upstream pull per source per UTC day: a source that already
// has an ok row for today is skipped, so a repeated call costs nothing
// upstream. That makes the function safe to call with the public key from
// pg_cron (supabase/migrations/draft_pull_schedule_20261127.sql).
// Body (optional JSON): {"sources": ["fantasypros_ecr", "espn"], "force": false}.
import {
  ESPN_FILTER, ESPN_URL, FP_CRAWL_DELAY_MS, FP_ECR_PAGES, parseEspn, parseFpEcr, SEASON,
} from "./parse.js";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const UA = "DDF-draft-pull/0";
const SOURCES = ["fantasypros_ecr", "espn"];

const rest = (path: string, init: RequestInit = {}) =>
  fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

const today = () => new Date().toISOString().slice(0, 10);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function alreadyPulled(source: string, date: string): Promise<boolean> {
  const r = await rest(`draft_pulls?select=id&source=eq.${source}&pull_date=eq.${date}&status=eq.ok&limit=1`);
  return r.ok && (await r.json()).length > 0;
}

async function logPull(row: Record<string, unknown>) {
  await rest("draft_pulls?on_conflict=pull_date,source", {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates" },
    body: JSON.stringify([row]),
  });
}

async function saveRows(date: string, rows: Record<string, unknown>[]) {
  for (let i = 0; i < rows.length; i += 500) {
    const chunk = rows.slice(i, i + 500).map((r) => ({ ...r, pull_date: date }));
    const r = await rest("draft_market_values?on_conflict=pull_date,source,scoring,source_player_id", {
      method: "POST",
      headers: { Prefer: "resolution=merge-duplicates" },
      body: JSON.stringify(chunk),
    });
    if (!r.ok) throw new Error(`save failed ${r.status}: ${(await r.text()).slice(0, 200)}`);
  }
}

async function pullFantasyPros() {
  const rows: Record<string, unknown>[] = [];
  const updated: Record<string, string | null> = {};
  let first = true;
  for (const [scoring, url] of Object.entries(FP_ECR_PAGES)) {
    if (!first) await sleep(FP_CRAWL_DELAY_MS);
    first = false;
    const r = await fetch(url, { headers: { "User-Agent": UA } });
    if (!r.ok) throw new Error(`fantasypros ${scoring}: HTTP ${r.status}`);
    const parsed = parseFpEcr(await r.text(), scoring, SEASON);
    updated[scoring] = parsed.sourceUpdatedAt;
    rows.push(...parsed.rows);
  }
  const stamps = Object.values(updated).filter(Boolean) as string[];
  return { rows, sourceUpdatedAt: stamps.sort().at(-1) ?? null, detail: { updated } };
}

async function pullEspn() {
  const r = await fetch(ESPN_URL(SEASON), { headers: { "User-Agent": UA, "X-Fantasy-Filter": ESPN_FILTER } });
  if (!r.ok) throw new Error(`espn: HTTP ${r.status}`);
  const parsed = parseEspn(await r.json(), SEASON);
  return { rows: parsed.rows, sourceUpdatedAt: null, detail: {} };
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("POST only", { status: 405 });
  let body: { sources?: string[]; force?: boolean } = {};
  try { body = await req.json(); } catch { /* empty body = defaults */ }
  const wanted = (body.sources ?? SOURCES).filter((s) => SOURCES.includes(s));
  const date = today();
  const results: Record<string, unknown> = {};
  for (const source of wanted) {
    if (!body.force && await alreadyPulled(source, date)) {
      results[source] = { status: "skipped", reason: "already pulled today" };
      continue;
    }
    try {
      const got = source === "espn" ? await pullEspn() : await pullFantasyPros();
      await saveRows(date, got.rows);
      const row = { pull_date: date, source, season: SEASON, status: "ok", rows: got.rows.length,
        source_updated_at: got.sourceUpdatedAt, detail: got.detail, pulled_at: new Date().toISOString() };
      await logPull(row);
      results[source] = row;
    } catch (e) {
      const row = { pull_date: date, source, season: SEASON, status: "failed", rows: 0,
        source_updated_at: null, detail: { error: String(e).slice(0, 500) }, pulled_at: new Date().toISOString() };
      await logPull(row);
      results[source] = row;
    }
  }
  return new Response(JSON.stringify({ pull_date: date, season: SEASON, label: `${SEASON} data`, results }), {
    headers: { "Content-Type": "application/json" },
  });
});
