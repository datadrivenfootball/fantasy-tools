// Draft tool 2026 outcome test (JEG-1667). How close each pre-draft price
// came to what players were actually worth: realized 2026 value = weeks 1-11
// fantasy points scaled to 17 games, priced through the same value build as
// ours (DDF Value -> league dollars). Three league shapes. Adapted from the
// third Opus review of bc19862 (its outcome probe); written here from scratch.
//
// Usage:
//   node tools/draft_outcome.mjs --fp fp.json --vegas vegas.json --espn espn.json \
//     --ecr-dir <dir> [--actuals data/inputs/weekly_actuals_2024_2026.csv] \
//     [--weeks 11] [--vegas-scale off] > outcome.json
// Prints a JSON report: per league, MAE and bias (predicted - realized $) by
// position for ours, market and platform, plus each one's position split.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { buildPrices, ecrRanks, espnTable } from "./draft_backtest.mjs";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const E = require(path.join(ROOT, "app", "draft", "draft-engine.js"));
const LINEUP = JSON.parse(fs.readFileSync(path.join(ROOT, "config", "lineup_parameters.json"), "utf8"));
const SKILL = ["QB", "RB", "WR", "TE"];

// The three shapes: the keeper room (12 teams, standard, 2 WR), Jeremy's
// USO league (12 teams, half PPR, 3 WR) and ESPN's default (10 teams, PPR).
export const LEAGUES = [
  { label: "Standard keeper room", column: "std", ecr: "standard",
    league: { teams: 12, budget: 200, minBid: 1, scoring: "standard", ecr: "standard",
      slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 5 } } },
  { label: "Half PPR (USO settings)", column: "half_ppr", ecr: "half",
    league: { teams: 12, budget: 200, minBid: 1, scoring: "yahoo_half", ecr: "half",
      slots: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 5 } } },
  { label: "ESPN PPR default", column: "ppr", ecr: "ppr",
    league: { teams: 10, budget: 200, minBid: 1, scoring: "ppr", ecr: "ppr",
      slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 7 } } },
];

// Realized points per player: season 2026, weeks 1..weeks, scaled to 17 games.
export function realizedPoints(csvText, column, weeks, keys) {
  const lines = csvText.trim().split("\n");
  const head = lines[0].split(",");
  const iS = head.indexOf("season"), iW = head.indexOf("week"), iK = head.indexOf("player_key"), iC = head.indexOf(column);
  if ([iS, iW, iK, iC].some(i => i < 0)) throw new Error(`actuals file lacks season/week/player_key/${column}`);
  const pts = {};
  lines.slice(1).forEach(l => {
    const r = l.split(",");
    if (r[iS] !== "2026" || +r[iW] > weeks || !keys.has(r[iK])) return;
    pts[r[iK]] = (pts[r[iK]] || 0) + Number(r[iC]);
  });
  const out = {};
  keys.forEach(k => { out[k] = (pts[k] || 0) * 17 / weeks; });
  return out;
}

// One common player set for every predictor: players the market prices above
// the minimum bid or whose realized value is above it. Neither ours nor the
// platform picks players, so the market row cannot move when ours's scaling
// does (fourth review of 31faf01).
export function commonSet(market, real, players, minBid) {
  return Object.keys(players).filter(k => (market[k] || 0) > minBid || (real[k] || 0) > minBid);
}

export function errors(maps, real, players, minBid) {
  const keys = commonSet(maps.market || {}, real, players, minBid);
  const out = {};
  Object.entries(maps).forEach(([name, m]) => {
    const by = {};
    keys.forEach(k => {
      const e = (m[k] || minBid) - (real[k] || minBid);
      for (const g of [players[k].pos, "ALL"]) { const s = (by[g] ||= { n: 0, abs: 0, bias: 0 }); s.n++; s.abs += Math.abs(e); s.bias += e; }
    });
    out[name] = Object.fromEntries(Object.entries(by).map(([g, s]) => [g, { n: s.n, mae: s.abs / s.n, bias: s.bias / s.n }]));
  });
  return { n: keys.length, byPredictor: out };
}

function split(m, players, minBid) {
  const t = {}; let all = 0;
  Object.entries(m).forEach(([k, v]) => { const p = players[k].pos; const s = Math.max(0, v - minBid); t[p] = (t[p] || 0) + s; all += s; });
  return Object.fromEntries(SKILL.map(p => [p, all ? (t[p] || 0) / all : 0]));
}

function main() {
  const a = {}; const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i += 2) a[argv[i].replace(/^--/, "")] = argv[i + 1];
  const rj = f => JSON.parse(fs.readFileSync(f, "utf8"));
  const fp = rj(a.fp), vegas = rj(a.vegas), espn = espnTable(rj(a.espn));
  const csv = fs.readFileSync(a.actuals || path.join(ROOT, "data", "inputs", "weekly_actuals_2024_2026.csv"), "utf8");
  const weeks = Number(a.weeks || 11);
  const vegasScale = a["vegas-scale"] === "off" ? false : undefined;
  const reports = LEAGUES.map(({ label, column, ecr, league }) => {
    const P = buildPrices({ league, fp, vegas, espn, ecr: ecrRanks(path.join(a["ecr-dir"], `ecr_${ecr}.html`)), vegasScale });
    const sh = E.leagueShape(league);
    const keys = new Set(Object.keys(P.players));
    const pts = realizedPoints(csv, column, weeks, keys);
    const players = Object.fromEntries([...keys].map(k => [k, P.players[k]]));
    const real = E.ddfDraftValues({ league, players, projections: { realized: pts }, lineupConfig: LINEUP });
    const realD = E.ourPrices(real, league);
    const maps = { ours: P.ours, market: P.market, platform: P.platform };
    return { label, league, weeks, vegasFactors: P.vegasFactors, vegasFactorBasis: P.vegasFactorBasis, sourceCounts: P.sourceCounts,
      ...errors(maps, realD, players, sh.minBid),
      split: Object.fromEntries(Object.entries({ realized: realD, ...maps }).map(([n, m]) => [n, split(m, players, sh.minBid)])) };
  });
  process.stdout.write(JSON.stringify({ generated: new Date().toISOString(), data: "2026 data", weeks, vegasScale: vegasScale !== false, reports }, null, 1));
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) main();
