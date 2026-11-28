// Turn a pasted sportsbook season-props page into one dated Vegas snapshot
// (JEG-1667). Same for every league. The snapshot has the shape of the
// 2026-09-12 export ([{name, player_key, team, market, line}]), so it feeds
// ours through the same path: `--vegas` in tools/draft_backtest.mjs and
// tools/draft_sim.mjs, and DraftEngine.ddfDraftValues({vegas}).
//
// Usage:
//   node tools/draft_vegas_paste.mjs --in paste.txt --players fp.json \
//     --season 2026 --date 2026-08-20 --out <dir>
// players: the FantasyPros projection export ([{key, name, pos, team}]).
// Fails closed: any unreadable prop line -> exit 1, the lines listed, no
// file written. Writes <out>/vegas_<date>.json and vegas_<date>.meta.json.
// --sql also writes vegas_<date>.sql: an idempotent load of that snapshot into
// public.draft_vegas_lines (it replaces that date's rows). Run it in the
// Supabase SQL editor or through the Supabase connector; no key is needed
// here, and the public key cannot write the table.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const V = require(path.join(ROOT, "app", "draft", "vegas-paste.js"));

const wantSql = process.argv.includes("--sql");
const argv = process.argv.slice(2).filter(x => x !== "--sql"), a = {};
for (let i = 0; i < argv.length; i += 2) a[argv[i].replace(/^--/, "")] = argv[i + 1];
for (const req of ["in", "players", "season", "date", "out"]) {
  if (!a[req]) { process.stderr.write(`--${req} is required\n`); process.exit(2); }
}
if (!/^\d{4}-\d{2}-\d{2}$/.test(a.date)) { process.stderr.write("--date must be YYYY-MM-DD\n"); process.exit(2); }

const list = JSON.parse(fs.readFileSync(a.players, "utf8"));
const players = Array.isArray(list)
  ? Object.fromEntries(list.map(p => [String(p.key), { name: p.name, pos: p.pos, team: p.team }]))
  : list;
const res = V.parse(fs.readFileSync(a.in, "utf8"), players, { season: Number(a.season), snapshotDate: a.date });
if (!res.ok) {
  process.stderr.write(`Not saved: ${res.errors.length} line(s) could not be read` +
    (res.rows.length ? "" : " and no prop lines were found") + "\n");
  res.errors.forEach(e => process.stderr.write(`  line ${e.lineNo}: ${e.text}  (${e.reason})\n`));
  process.exit(1);
}
const rows = res.rows.map(r => ({ name: r.name, player_key: Number(r.key), team: r.team, market: r.market, line: r.line }));
fs.mkdirSync(a.out, { recursive: true });
const file = path.join(a.out, `vegas_${a.date}.json`);
fs.writeFileSync(file, JSON.stringify(rows, null, 1));
fs.writeFileSync(path.join(a.out, `vegas_${a.date}.meta.json`), JSON.stringify({
  snapshot_date: a.date, pulled_at: new Date().toISOString(), season: res.season, label: `${res.season} data`, source: "paste",
  rows: rows.length, players: new Set(rows.map(r => r.player_key)).size, ignored_lines: res.ignored,
  // No scale factors are stored: the engine recomputes them on every build
  // from the projection it prices (fourth review of 31faf01: stored factors
  // were never read back).
  vegas_scale: "recomputed by the engine at build time",
}, null, 1));
if (wantSql) {
  const q = v => (v === null || v === undefined ? "null" : `'${String(v).replace(/'/g, "''")}'`);
  const values = rows.map(r => `  ('${a.date}', ${Number(res.season)}, 'paste', ${r.player_key}, ${q(r.name)}, ${q(r.team)}, ${q(r.market)}, ${Number(r.line)})`);
  fs.writeFileSync(path.join(a.out, `vegas_${a.date}.sql`), [
    `-- Pasted Vegas season props, snapshot ${a.date} (${res.season} data), ${rows.length} lines. Idempotent.`,
    "begin;",
    `delete from public.draft_vegas_lines where snapshot_date = '${a.date}';`,
    "insert into public.draft_vegas_lines (snapshot_date, season, source, player_key, player_name, team, market, line) values",
    values.join(",\n") + ";",
    "commit;", ""].join("\n"));
}
process.stdout.write(`Saved ${rows.length} lines for ${new Set(rows.map(r => r.player_key)).size} players to ${file}\n`);
