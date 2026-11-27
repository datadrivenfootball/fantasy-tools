// Node driver for the draft engine tests (JEG-1667).
//
// Usage: node tests/draft_engine_driver.js <case> [args...]
//   worked <fixture.json> [variant]   board for the worked-example auction
//   pricing <fixture.json>            prices for the worked-example weights
//   build <input.json>                ours/market prices for a full league
// Prints JSON on stdout.
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DraftEngine = require(path.join(ROOT, "app", "draft", "draft-engine.js"));

const [mode, file, variant] = process.argv.slice(2);
const doc = JSON.parse(fs.readFileSync(file, "utf8"));

function workedState(auction, teams) {
  const pos = {}, ours = {}, market = {};
  Object.entries(auction.players).forEach(([k, p]) => { pos[k] = p.pos; ours[k] = p.ours; market[k] = p.market; });
  return { league: auction.league, me: auction.me, teams, available: Object.keys(auction.players),
    pos, prices: { ours, market } };
}

let out;
if (mode === "pricing") {
  const prices = DraftEngine.pricesFromWeights(doc.pricing.weights, doc.pricing.league);
  out = { prices, shape: DraftEngine.leagueShape(doc.pricing.league) };
} else if (mode === "worked") {
  const a = doc.auction;
  const teams = variant ? a[variant].teams : a.teams;
  out = DraftEngine.board(workedState(a, teams));
} else if (mode === "build") {
  const res = DraftEngine.ddfDraftValues(doc);
  const ours = DraftEngine.ourPrices(res.values, doc.league);
  out = { values: res.values, ours, snake: DraftEngine.snakeRanks(res.values),
    method: res.pipeline.method, benchShare: res.pipeline.benchShare, basis: res.basis,
    shape: DraftEngine.leagueShape(doc.league) };
} else {
  throw new Error(`unknown mode ${mode}`);
}
process.stdout.write(JSON.stringify(out));
