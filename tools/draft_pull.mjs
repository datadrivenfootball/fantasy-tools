// Draft tool daily pull, local runner (JEG-1667, Phase 0). Same parsers as
// the edge function (supabase/functions/draft-pull/parse.js). Fetches the
// sources once and writes <out>/draft-pull-<pull_date>.json with the pull
// date, the season the sources state, per-source status and every row.
// Writes nothing to Supabase.
//
// Usage: node tools/draft_pull.mjs --out <dir> [--sources fantasypros_ecr,espn]
import fs from "node:fs";
import path from "node:path";
import {
  ESPN_FILTER, ESPN_URL, FP_CRAWL_DELAY_MS, FP_ECR_PAGES, parseEspn, parseFpEcr, SEASON,
} from "../supabase/functions/draft-pull/parse.js";

const UA = "DDF-draft-pull/0";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const arg = (name, dflt) => {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? dflt : process.argv[i + 1];
};

async function fantasyPros() {
  const rows = [], updated = {};
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
  return { rows, sourceUpdatedAt: Object.values(updated).filter(Boolean).sort().at(-1) ?? null, detail: { updated } };
}

async function espn() {
  const r = await fetch(ESPN_URL(SEASON), { headers: { "User-Agent": UA, "X-Fantasy-Filter": ESPN_FILTER } });
  if (!r.ok) throw new Error(`espn: HTTP ${r.status}`);
  return { rows: parseEspn(await r.json(), SEASON).rows, sourceUpdatedAt: null, detail: {} };
}

async function main() {
  const out = arg("out");
  if (!out) throw new Error("--out <dir> is required");
  const sources = arg("sources", "fantasypros_ecr,espn").split(",");
  const pullDate = new Date().toISOString().slice(0, 10);
  const pulls = [], rows = [];
  for (const source of sources) {
    try {
      const got = source === "espn" ? await espn() : await fantasyPros();
      rows.push(...got.rows.map((r) => ({ ...r, pull_date: pullDate })));
      pulls.push({ pull_date: pullDate, source, season: SEASON, status: "ok", rows: got.rows.length,
        source_updated_at: got.sourceUpdatedAt, detail: got.detail, pulled_at: new Date().toISOString() });
    } catch (e) {
      pulls.push({ pull_date: pullDate, source, season: SEASON, status: "failed", rows: 0,
        detail: { error: String(e) }, pulled_at: new Date().toISOString() });
    }
  }
  fs.mkdirSync(out, { recursive: true });
  const file = path.join(out, `draft-pull-${pullDate}.json`);
  fs.writeFileSync(file, JSON.stringify({ pull_date: pullDate, season: SEASON, label: `${SEASON} data`, pulls, rows }));
  process.stdout.write(JSON.stringify({ file, pulls }, null, 1) + "\n");
  if (pulls.some((p) => p.status !== "ok")) process.exitCode = 1;
}

main();
