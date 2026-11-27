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
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const V = require(path.join(ROOT, "app", "draft", "vegas-paste.js"));

const argv = process.argv.slice(2), a = {};
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
  snapshot_date: a.date, season: res.season, label: `${res.season} data`, source: "paste",
  rows: rows.length, players: new Set(rows.map(r => r.player_key)).size, ignored_lines: res.ignored,
}, null, 1));
process.stdout.write(`Saved ${rows.length} lines for ${new Set(rows.map(r => r.player_key)).size} players to ${file}\n`);
