// Draft tool Phase 0: seeded auction simulator (JEG-1667). Engine and tools
// only, no UI. Runs many 12-team auctions per push-floor policy with the same
// seeds (common random numbers), so policies differ only by our bids.
//
// Usage:
//   node tools/draft_sim.mjs --fp fp.json --vegas vegas.json --espn espn.json \
//     --ecr-dir <dir> [--drafts 200] [--seed 1] > sim.json
//
// League: Jeremy's 2026 auction league settings (12 teams, half PPR with
// Yahoo scoring, QB/2RB/3WR/TE/FLEX/K/DEF/5 bench). Budget $200 is assumed.
// K and DEF are $1 slots: their $2 is taken off each budget up front.
// Prices: the engine's ours (blend 50/25/25), market (FantasyPros 2026 ECR on
// ESPN's curve) and platform (ESPN 2026 values), all 2026 data.
//
// Rivals: each rival's limit for a player = room price now (engine opponent
// model, market/platform blend, inflated) x its own seeded noise (lognormal,
// sigma 0.2) x need (1 starting slot, 0.6 bench only), capped at its max bid.
// Rivals nominate at random among the three priciest players they can roster.
// Sale: the highest limit wins at the runner-up's limit + $1 (English
// auction); ties break by seed.
//
// We use the engine: nominations from nominationPlays, bids by policy:
//   walkaway  bid to walk-away on everyone (league price, no push logic)
//   A         walk-away on targets and neutrals, push floor A on fades
//   B         our roster value (buy limit) on everyone
//   C         B on targets; B plus bounded overreach (push floor C) otherwise
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { buildPrices, ecrRanks, espnTable } from "./draft_backtest.mjs";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const E = require(path.join(ROOT, "app", "draft", "draft-engine.js"));

// Policy = bid rule + which inflation factor sets our walk-away.
export const POLICIES = [
  { name: "walkaway-room", rule: "walkaway", factor: "room" },
  { name: "walkaway", rule: "walkaway", factor: "personal" },
  { name: "A", rule: "A", factor: "personal" },
  { name: "B", rule: "B", factor: "personal" },
  { name: "C", rule: "C", factor: "personal" },
];
const STARTERS = { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1 };
const NOISE_SIGMA = 0.2;

// Deterministic per-(draft, team, player) random numbers: the same rival
// noise in every policy.
function hash32(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i += 1) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}
function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const uniform = (...parts) => mulberry32(hash32(parts.join("|")))();
function gauss(...parts) {
  const u1 = Math.max(1e-12, uniform(...parts, "a")), u2 = uniform(...parts, "b");
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

// Inverse standard normal (Acklam's rational approximation, |error| < 1.2e-9).
function invNorm(p) {
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const lo = 0.02425;
  if (p < lo) { const q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  if (p > 1 - lo) return -invNorm(1 - p);
  const q = p - 0.5, r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}
// Expected second-largest of n standard normals (Blom). Rival noise is
// shifted down by this so the expected runner-up limit equals the room price:
// rooms pay about market on average (backtest), not market plus the noise.
function runnerUpShift(n) {
  return n >= 2 ? invNorm((n - 1 - 0.375) / (n + 0.25)) : 0;
}

function slotFor(open, pos) {
  if ((open[pos] || 0) > 0) return pos;
  if (["RB", "WR", "TE"].includes(pos) && (open.FLEX || 0) > 0) return "FLEX";
  if ((open.BN || 0) > 0) return "BN";
  return null;
}

// Best lineup value of a roster under one value map.
export function starterValue(roster, pos, val) {
  const byPos = { QB: [], RB: [], WR: [], TE: [] };
  roster.forEach(k => byPos[pos[k]] && byPos[pos[k]].push(k));
  Object.values(byPos).forEach(l => l.sort((a, b) => (val[b] || 0) - (val[a] || 0)));
  let total = 0;
  const left = [];
  ["QB", "RB", "WR", "TE"].forEach(p => {
    byPos[p].forEach((k, i) => { if (i < STARTERS[p]) total += val[k] || 0; else if (p !== "QB") left.push(k); });
  });
  left.sort((a, b) => (val[b] || 0) - (val[a] || 0)).slice(0, STARTERS.FLEX).forEach(k => { total += val[k] || 0; });
  return total;
}

export function simulate({ prices, league, policy: pol, draft, seed, teams = 12 }) {
  const policy = pol.rule;
  const simLeague = { teams, budget: league.budget - (league.slots.K + league.slots.DST) * league.minBid,
    minBid: league.minBid, slots: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BN: league.slots.BN } };
  const pos = Object.fromEntries(Object.entries(prices.players).map(([k, p]) => [k, p.pos]));
  const me = Math.floor(uniform(seed, draft, "me") * teams);
  const state = {
    league: simLeague, me,
    teams: Array.from({ length: teams }, (_, id) => ({ id, budgetLeft: simLeague.budget, open: { ...simLeague.slots } })),
    // Every projected player is draftable; unpriced ones go for about $1.
    available: Object.keys(prices.players),
    pos, prices: { ours: prices.ours, market: prices.market, platform: prices.platform },
    ourFactor: pol.factor,
  };
  const rosters = Array.from({ length: teams }, () => []);
  const ours = { buys: [], pushWins: 0, aboveValue: 0, aboveValueDollars: 0, aboveWalkAway: 0, drained: 0 };
  const rivalSales = [];
  let nominator = Math.floor(uniform(seed, draft, "first") * teams);
  const openTotal = t => Object.values(t.open).reduce((a, b) => a + b, 0);
  // A team that still has open slots but no player left who fits them can
  // neither nominate nor buy (a real league fills it from waivers).
  const canStillBuy = t => openTotal(t) > 0 && state.available.some(k => slotFor(t.open, pos[k]));
  let guard = 0;
  while (state.teams.some(canStillBuy) && guard < 1000) {
    guard += 1;
    while (!canStillBuy(state.teams[nominator])) nominator = (nominator + 1) % teams;
    const nomTeam = state.teams[nominator];
    let key;
    if (nominator === me) {
      const plays = E.nominationPlays(state, { limit: 1 });
      key = plays.length ? plays[0].key : null;
    }
    if (!key) {
      const can = state.available.filter(k => slotFor(nomTeam.open, pos[k]))
        .sort((a, b) => (prices.market[b] || 0) - (prices.market[a] || 0) || (a < b ? -1 : 1)).slice(0, 3);
      key = can[Math.floor(uniform(seed, draft, guard, "nom") * can.length)];
    }
    if (!key) break;
    const cache = { ours: E.inflation(state, state.prices.ours), market: E.inflation(state, state.prices.market),
      platform: E.inflation(state, state.prices.platform) };
    const model = E.opponentModel(state, key, { cache });
    const bids = [];
    const nRivals = state.teams.filter(t => t.id !== me && openTotal(t) > 0 && slotFor(t.open, pos[key])).length;
    const shift = runnerUpShift(nRivals);
    state.teams.forEach(t => {
      if (openTotal(t) === 0 || !slotFor(t.open, pos[key])) return;
      const mb = E.maxBid(t, simLeague);
      if (mb < simLeague.minBid) return;
      let limit;
      let mode = "buy";
      if (t.id === me) {
        const pf = E.pushFloors(state, key, { cache });
        const row = pf;
        if (policy === "walkaway") limit = row.walkAway;
        else if (policy === "A") { limit = pf.classification === "fade" ? (pf.pushFloor.A || 0) : row.walkAway; mode = pf.classification === "fade" ? "push" : "buy"; }
        else if (policy === "B") limit = pf.buyLimit;
        else { limit = pf.classification === "target" ? pf.buyLimit : (pf.pushFloor.C || 0); mode = (pf.pushFloor.C || 0) > pf.buyLimit ? "push" : "buy"; }
        bids.push({ id: t.id, limit: Math.max(0, limit), mode, value: pf.rosterValue, walkAway: pf.walkAway });
      } else {
        const need = E.needFactor(t, pos[key]);
        const noise = Math.exp(NOISE_SIGMA * (gauss(seed, draft, t.id, key) - shift));
        const room = model.roomPrice == null ? simLeague.minBid : model.roomPrice;
        limit = Math.min(mb, Math.floor(room * noise * need + 1e-9));
        if (t.id === nominator) limit = Math.max(limit, simLeague.minBid);
        bids.push({ id: t.id, limit: Math.max(0, limit) });
      }
    });
    const live = bids.filter(b => b.limit >= simLeague.minBid);
    if (!live.length) {
      // Nobody will pay $1: the nominator takes him at $1 if it can.
      live.push({ id: nominator, limit: simLeague.minBid });
    }
    live.sort((a, b) => b.limit - a.limit || uniform(seed, draft, guard, a.id) - uniform(seed, draft, guard, b.id));
    const win = live[0];
    const second = live.length > 1 ? live[1].limit : 0;
    const price = Math.max(simLeague.minBid, Math.min(win.limit, second + simLeague.minBid));
    const team = state.teams[win.id];
    const slot = slotFor(team.open, pos[key]);
    team.open[slot] -= 1;
    team.budgetLeft -= price;
    rosters[win.id].push(key);
    state.available = state.available.filter(k => k !== key);
    if (win.id !== me && live.length > 1 && live[1].id === me) {
      // We set the price: what the winner would have paid without us.
      const third = live.length > 2 ? live[2].limit : 0;
      const without = Math.max(simLeague.minBid, Math.min(win.limit, third + simLeague.minBid));
      ours.drained += price - without;
    }
    if (win.id === me) {
      ours.buys.push({ key, price });
      if (price > win.walkAway) ours.aboveWalkAway += 1;
      if (win.mode === "push") ours.pushWins += 1;
      if (price > win.value + 1e-9) { ours.aboveValue += 1; ours.aboveValueDollars += price - win.value; }
    } else {
      rivalSales.push({ key, price });
    }
    nominator = (nominator + 1) % teams;
  }
  const roster = rosters[me];
  const vals = prices.values;
  return {
    starterValue: starterValue(roster, pos, vals),
    rosterValue: roster.reduce((t, k) => t + (vals[k] || 0), 0),
    starterDollars: starterValue(roster, pos, prices.ours),
    unspent: state.teams[me].budgetLeft - Object.values(state.teams[me].open).reduce((a, b) => a + b, 0) * simLeague.minBid,
    pushWins: ours.pushWins,
    aboveValue: ours.aboveValue,
    aboveValueDollars: ours.aboveValueDollars,
    rivalOverpay: rivalSales.reduce((t, s) => t + (s.price - (prices.ours[s.key] || 0)), 0),
    drained: ours.drained,
    aboveWalkAway: ours.aboveWalkAway,
    filled: openTotal(state.teams[me]) === 0,
    openLeft: Object.fromEntries(Object.entries(state.teams[me].open).filter(([, v]) => v > 0)),
    sales: guard, poolLeft: state.available.length,
  };
}

function summarize(runs) {
  const mean = f => runs.reduce((t, r) => t + r[f], 0) / runs.length;
  const sd = f => { const m = mean(f); return Math.sqrt(runs.reduce((t, r) => t + (r[f] - m) ** 2, 0) / Math.max(1, runs.length - 1)); };
  return {
    drafts: runs.length,
    starterValue: mean("starterValue"), starterValueSd: sd("starterValue"),
    rosterValue: mean("rosterValue"), starterDollars: mean("starterDollars"),
    unspent: mean("unspent"), pushWins: mean("pushWins"),
    aboveValue: mean("aboveValue"), aboveValueDollars: mean("aboveValueDollars"),
    aboveWalkAway: mean("aboveWalkAway"), drained: mean("drained"),
    rivalOverpay: mean("rivalOverpay"),
    filledShare: runs.filter(r => r.filled).length / runs.length,
  };
}

function main() {
  const a = {};
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i += 2) a[argv[i].replace(/^--/, "")] = argv[i + 1];
  const drafts = Number(a.drafts || 200), seed = Number(a.seed || 1);
  const league = { teams: 12, budget: 200, minBid: 1, scoring: "yahoo_half", ecr: "half",
    slots: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, K: 1, DST: 1, BN: 5 } };
  const prices = buildPrices({ league, fp: JSON.parse(fs.readFileSync(a.fp, "utf8")),
    vegas: JSON.parse(fs.readFileSync(a.vegas, "utf8")), espn: espnTable(JSON.parse(fs.readFileSync(a.espn, "utf8"))),
    ecr: ecrRanks(path.join(a["ecr-dir"], "ecr_half.html")) });
  const results = {};
  POLICIES.forEach(policy => {
    const runs = [];
    for (let d = 0; d < drafts; d += 1) runs.push(simulate({ prices, league, policy, draft: d, seed }));
    results[policy.name] = { ...summarize(runs), rule: policy.rule, factor: policy.factor };
  });
  process.stdout.write(JSON.stringify({ generated: new Date().toISOString(), data: "2026 data", league,
    drafts, seed, noiseSigma: NOISE_SIGMA, opponentDefaults: E.OPPONENT_DEFAULTS, results }, null, 1));
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) main();
