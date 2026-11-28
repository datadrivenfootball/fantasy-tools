// Draft tool data bundle (JEG-1667, Phase 1): reads the same public Supabase
// tables the page reads (app/draft/draft-data.js, publishable key, read
// only) and writes the assembled bundle as JSON. Used for the review
// preview and for checking the page's data offline. Writes nothing to
// Supabase. The bundle holds third-party numbers: keep it out of the repo.
//
// Usage: node tools/draft_bundle.mjs --out <file.json>
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const DraftData = require(path.join(ROOT, "app", "draft", "draft-data.js"));

const i = process.argv.indexOf("--out");
if (i === -1) throw new Error("--out <file.json> is required");
const names = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const fetchWithNames = (url, init) => String(url).endsWith("players-table-1.json")
  ? Promise.resolve({ ok: true, json: async () => names })
  : fetch(url, init);
const bundle = await DraftData.loadSupabase({ fetch: fetchWithNames });
fs.writeFileSync(process.argv[i + 1], JSON.stringify(bundle));
const count = (f) => bundle.players.filter(f).length;
process.stdout.write(JSON.stringify({ out: process.argv[i + 1], season: bundle.season, asOf: bundle.asOf,
  players: bundle.players.length, withProjection: count((p) => p.proj), withVegas: count((p) => p.vegas),
  withEcrHalf: count((p) => p.ecr.HALF), withEspn: count((p) => p.espn.PPR != null), dropped: bundle.dropped }, null, 1) + "\n");
