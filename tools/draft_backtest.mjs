// Draft tool Phase 0 backtest (JEG-1667): price error by position against
// real 2026 auctions. Reads local input files (kept out of the repo: they
// hold third-party data) and prints a JSON report.
//
// Usage:
//   node tools/draft_backtest.mjs --fp fp.json --vegas vegas.json \
//     --espn espn_2026.json --ecr-dir <dir with ecr_{standard,half,ppr}.html> \
//     [--auction name=file.json:league.json ...] > report.json
//
// Inputs:
//   fp     FantasyPros 2026 season projections, one snapshot: [{key, name,
//          pos, team, pass_yds, pass_tds, ints, rush_yds, rush_tds, rec,
//          rec_yds, rec_tds, fum_lost}]
//   vegas  2026 season prop lines: [{name, team, market, line}]
//   espn   ESPN kona_player_info for 2026 (platform values, AAV)
//   ecr    FantasyPros 2026 draft ECR pages (ecrData embedded in the HTML)
//   auction  [{name, price, keeper}] sales, with a league JSON
//            {teams, budget, minBid, scoring, slots}
//
// Predictors, each priced for the auction's league before any sale:
//   ours      DDF draft value (FP + Vegas projections, FP ECR market) in $
//   market    FP ECR mapped onto ESPN's published dollar curve
//   platform  ESPN's published auction values
// Keepers are treated as already sold: predictions are inflated by the
// draft-start inflation of each price map (engine.inflation).
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const E = require(path.join(ROOT, "app", "draft", "draft-engine.js"));
const LINEUP = JSON.parse(fs.readFileSync(path.join(ROOT, "config", "lineup_parameters.json"), "utf8"));
const SKILL = ["QB", "RB", "WR", "TE"];

function args() {
  const a = process.argv.slice(2), out = { auction: [] };
  for (let i = 0; i < a.length; i += 2) {
    const k = a[i].replace(/^--/, "");
    if (k === "auction") out.auction.push(a[i + 1]); else out[k] = a[i + 1];
  }
  return out;
}
const readJson = f => JSON.parse(fs.readFileSync(f, "utf8"));

// Nicknames a source spells differently (checked by hand against FP names).
const NAME_ALIASES = { "kenny gainwell": "kenneth gainwell" };

export function normName(s) {
  const n = normBase(s);
  return NAME_ALIASES[n] || n;
}

function normBase(s) {
  return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[.'’]/g, "").replace(/-/g, " ").replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "")
    .replace(/\s+/g, " ").trim();
}

// The JSON object starting at text[start] (string-aware brace matching).
function balancedObject(text, start) {
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < text.length; i += 1) {
    const c = text[i];
    if (inStr) { if (esc) esc = false; else if (c === "\\") esc = true; else if (c === '"') inStr = false; continue; }
    if (c === '"') inStr = true;
    else if (c === "{") depth += 1;
    else if (c === "}" && --depth === 0) return text.slice(start, i + 1);
  }
  throw new Error("unbalanced JSON object");
}

function ecrRanks(file) {
  const t = fs.readFileSync(file, "utf8");
  const m = /ecrData\s*=\s*/.exec(t);
  const d = JSON.parse(balancedObject(t, m.index + m[0].length));
  const out = new Map();
  d.players.filter(p => SKILL.includes(p.player_position_id))
    .forEach(p => out.set(normName(p.player_name), Number(p.rank_ecr)));
  return { ranks: out, lastUpdated: d.last_updated, year: d.year, scoring: d.scoring };
}

const ESPN_POS = { 1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST" };
function espnTable(doc) {
  return doc.players.map(r => r.player).map(p => ({
    name: normName(p.fullName), pos: ESPN_POS[p.defaultPositionId],
    std: p.draftRanksByRankType?.STANDARD?.auctionValue ?? null,
    ppr: p.draftRanksByRankType?.PPR?.auctionValue ?? null,
    aav: p.ownership?.auctionValueAverage ?? null,
  }));
}

function buildPrices({ league, fp, vegas, espn, ecr }) {
  // league.ecr names the published format closest to the league's scoring.
  const scoringKey = league.ecr === "standard" ? "std" : "ppr";
  const players = {}, fpStats = {}, byName = new Map();
  fp.forEach(r => {
    const k = String(r.key);
    players[k] = { pos: r.pos, name: r.name };
    fpStats[k] = Object.fromEntries(Object.entries(r).map(([f, v]) => [f, typeof v === "string" && f !== "name" && f !== "pos" && f !== "team" ? Number(v) : v]));
    byName.set(normName(r.name), k);
  });
  const lines = {};
  vegas.forEach(v => {
    const k = byName.get(normName(v.name));
    if (!k) return;
    (lines[k] ||= {})[v.market] = Number(v.line);
  });
  const vegasStats = {};
  Object.entries(lines).forEach(([k, l]) => { const s = E.vegasStatLine(l, fpStats[k]); if (s) vegasStats[k] = s; });
  const espnSkill = espn.filter(p => SKILL.includes(p.pos));
  const curve = espnSkill.map(p => p[scoringKey]).filter(v => v != null && v > 0);
  const ecrByKey = {};
  for (const [nm, rank] of ecr.ranks) { const k = byName.get(nm); if (k) ecrByKey[k] = rank; }
  const fpMarketRaw = E.rankImpliedDollars(ecrByKey, curve);
  const platformRaw = {};
  espnSkill.forEach(p => { const k = byName.get(p.name); if (k && p[scoringKey] != null) platformRaw[k] = p[scoringKey]; });
  const build = E.ddfDraftValues({ league, players, projections: { fp: fpStats, vegas: vegasStats },
    markets: { fp_ecr: fpMarketRaw }, lineupConfig: LINEUP });
  return {
    players, byName,
    ours: E.ourPrices(build.values, league),
    market: E.rescaleDollars(fpMarketRaw, league),
    platform: E.rescaleDollars(platformRaw, league),
    method: build.pipeline.method,
    coverage: { fp: Object.keys(fpStats).length, vegas: Object.keys(vegasStats).length,
      ecr: Object.keys(ecrByKey).length, platform: Object.keys(platformRaw).length },
  };
}

// scale: multiply predictions by this before scoring (1 = raw dollars).
function summarize(rows, field, scale = 1) {
  const byPos = {};
  rows.forEach(r => {
    const e = r[field] * scale - r.actual;
    const s = (byPos[r.pos] ||= { n: 0, abs: 0, bias: 0 });
    s.n += 1; s.abs += Math.abs(e); s.bias += e;
    const t = (byPos.ALL ||= { n: 0, abs: 0, bias: 0 });
    t.n += 1; t.abs += Math.abs(e); t.bias += e;
  });
  const out = {};
  Object.entries(byPos).forEach(([p, s]) => { out[p] = { n: s.n, mae: s.abs / s.n, bias: s.bias / s.n }; });
  return out;
}

function backtest(name, sales, league, inputs) {
  const prices = buildPrices({ league, ...inputs });
  const sh = E.leagueShape(league);
  const matched = [], unmatched = [], keepers = [];
  sales.forEach(s => {
    const k = prices.byName.get(normName(s.name));
    const row = { key: k, name: s.name, price: Number(s.price), keeper: !!s.keeper };
    if (row.keeper) keepers.push(row);
    if (!k) { if (!row.keeper) unmatched.push(s.name); return; }
    row.pos = prices.players[k].pos;
    if (!row.keeper) matched.push(row);
  });
  // Draft-start state: keepers sold; every other slot open.
  const keptMoney = keepers.reduce((t, r) => t + r.price, 0);
  const state = {
    league, me: "room",
    teams: [{ id: "room", budgetLeft: sh.teams * sh.budget - keptMoney,
      open: { BN: sh.teams * sh.valuedSlotsPerTeam - keepers.length, K: sh.teams * sh.slots.K, DST: sh.teams * sh.slots.DST } }],
    available: Object.keys(prices.players).filter(k => !keepers.some(r => r.key === k)),
    pos: Object.fromEntries(Object.entries(prices.players).map(([k, p]) => [k, p.pos])),
  };
  const factors = {};
  const rows = matched.map(r => ({ name: r.name, pos: r.pos, actual: r.price }));
  ["ours", "market", "platform"].forEach(f => {
    const inf = E.inflation(state, prices[f]);
    factors[f] = inf.factor;
    matched.forEach((r, i) => {
      const p = prices[f][r.key];
      rows[i][f] = p ? E.inflatedPrice(p, inf.factor, sh.minBid) : sh.minBid;
    });
  });
  return { name, league, method: prices.method, coverage: prices.coverage,
    sales: sales.length, keepers: keepers.length, keeperDollars: keptMoney,
    scored: rows.length, unmatched, inflationAtStart: factors,
    error: Object.fromEntries(["ours", "market", "platform"].map(f => [f, summarize(rows, f)])),
    // Shape only: each predictor scaled so its total over the scored players
    // equals what the room paid for them (removes a level mismatch).
    errorScaled: Object.fromEntries(["ours", "market", "platform"].map(f => {
      const paid = rows.reduce((t, r) => t + r.actual, 0), pred = rows.reduce((t, r) => t + r[f], 0);
      return [f, summarize(rows, f, pred > 0 ? paid / pred : 1)];
    })),
    rows };
}

function main() {
  const a = args();
  const fp = readJson(a.fp), vegas = readJson(a.vegas);
  const espn = espnTable(readJson(a.espn));
  const ecrFor = sc => ecrRanks(path.join(a["ecr-dir"], `ecr_${sc}.html`));
  const reports = [];
  a.auction.forEach(spec => {
    const [name, rest] = spec.split("=");
    const [salesFile, leagueFile] = rest.split(":");
    const league = readJson(leagueFile);
    reports.push(backtest(name, readJson(salesFile), league,
      { fp, vegas, espn, ecr: ecrFor(league.ecr) }));
  });
  // ESPN average auction values: the mean price across real 2026 ESPN
  // auctions, in ESPN's default auction league (10 teams, $200, PPR).
  const espnLeague = { teams: 10, budget: 200, minBid: 1, scoring: "ppr", ecr: "ppr",
    slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 7 } };
  const aavSales = espn.filter(p => SKILL.includes(p.pos) && p.aav >= 1)
    .map(p => ({ name: p.name, price: p.aav, keeper: false }));
  const espnRep = backtest("ESPN 2026 average auction values", aavSales, espnLeague,
    { fp, vegas, espn, ecr: ecrFor("ppr") });
  // ESPN's published values against ESPN's own rooms is not an independent
  // test (rooms anchor on the values shown), so the platform column is left out.
  delete espnRep.error.platform; delete espnRep.errorScaled.platform;
  reports.push(espnRep);
  const ecrMeta = ["standard", "half", "ppr"].map(sc => { const e = ecrFor(sc); return { scoring: e.scoring, year: e.year, lastUpdated: e.lastUpdated }; });
  process.stdout.write(JSON.stringify({ generated: new Date().toISOString(), data: "2026 data", ecr: ecrMeta, reports }, null, 1));
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) main();
