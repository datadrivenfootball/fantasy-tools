// Turn a pasted auction draft results page into the backtest's auction file
// (JEG-1667; Jeremy, 2026-11-27: "Paste USO XVIII"). Team and manager names
// are not kept.
//
// Usage:
//   node tools/draft_auction_paste.mjs --in paste.txt --players fp.json \
//     --league tools/draft_leagues/uso-season-xviii-2026.json --out uso_2026.json
// players: the FantasyPros projection export ([{key, name, pos, team}]).
// Then: node tools/draft_backtest.mjs ... --auction "uso=uso_2026.json:<league json>"
// Fails closed: any unreadable sale -> exit 1, the lines listed, no file.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const A = require(path.join(ROOT, "app", "draft", "auction-paste.js"));

const argv = process.argv.slice(2), a = {};
for (let i = 0; i < argv.length; i += 2) a[argv[i].replace(/^--/, "")] = argv[i + 1];
for (const req of ["in", "players", "league", "out"]) {
  if (!a[req]) { process.stderr.write(`--${req} is required\n`); process.exit(2); }
}
const league = JSON.parse(fs.readFileSync(a.league, "utf8"));
const list = JSON.parse(fs.readFileSync(a.players, "utf8"));
const rows = list.map(p => ({ player_key: p.key ?? p.player_key, name: p.name, pos: p.pos, team: p.team }));
const res = A.parse(fs.readFileSync(a.in, "utf8"), rows, { budget: league.budget });
if (!res.ok) {
  process.stderr.write(`Not saved: ${res.errors.length} line(s) could not be read` +
    (res.sales.length ? "" : " and no sales were found") + "\n");
  res.errors.forEach(e => process.stderr.write(`  line ${e.lineNo}: ${e.text}  (${e.reason})\n`));
  process.exit(1);
}
const slots = Object.values(league.slots).reduce((x, y) => x + y, 0);
const sold = res.sales.length + res.kdef.length;
const warn = [];
if (res.total > league.teams * league.budget) warn.push(`sales total $${res.total} is over ${league.teams} x $${league.budget}`);
if (sold !== league.teams * slots) warn.push(`${sold} sales read; a full draft is ${league.teams * slots}`);
fs.writeFileSync(a.out, JSON.stringify(res.sales.map(s => ({ name: s.name, price: s.price, keeper: s.keeper })), null, 1));
process.stdout.write(`Saved ${res.sales.length} skill-player sales (${res.keepers} keepers; ${res.kdef.length} K/DEF read and left out), total $${res.total}, to ${a.out}\n`);
warn.forEach(w => process.stdout.write(`Check: ${w}\n`));
