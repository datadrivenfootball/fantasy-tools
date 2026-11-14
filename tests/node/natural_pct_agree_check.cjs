// JEG-1639: the Natural fit label and the Why text's roster percent never disagree. Over every pairing of the league
// fixtures (tests/fixtures/league, synthetic engine rows as in tests/league_harness.cjs), each trade findTrades lists is
// judged by finder.js tradeFit and by ddf-opportunity.js rosterImprovementPct (the Why text's number) with the same
// context. Fails when a Natural fit has their roster clearly worse, or when the two percents differ.
//   node natural_pct_agree_check.cjs <finder.js> <ddf-opportunity.js> <fixtures dir>
// Prints {pairs, trades, natural, wouldBeNatural, clearlyWorse, failures: [..]}.
"use strict";
const path = require("path");
const fs = require("fs");
const Module = require("module");
const finderPath = path.resolve(process.argv[2]);
const oppPath = path.resolve(process.argv[3]);
const fixDir = path.resolve(process.argv[4]);
const F = require(finderPath);
// ddf-opportunity.js requires "../v2/finder.js"; point that at the finder under test.
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...rest) {
  if (/v2\/finder\.js$/.test(request)) return finderPath;
  return origResolve.call(this, request, parent, ...rest);
};
const O = require(oppPath);

const CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const ANALYST = ["cbs", "usatoday", "fantasypros"];
function hash(text) { let h = 2166136261; for (const c of String(text)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; }
const unit = (key, salt) => (hash(`${key}:${salt}`) % 10000) / 10000;
function makeRows(players) {
  const map = new Map();
  players.forEach(p => {
    if (String(p.key).startsWith("x:") || map.has(String(p.key))) return;
    const ddf = Math.round((4 + 36 * Math.pow(unit(p.key, "d"), 1.6)) * 10) / 10;
    const values = {ddf_value: ddf, ddf_value_projections: ddf, ddf_value_charts: ddf};
    const market = 0.62 + 0.76 * unit(p.key, "m");
    CH.forEach(k => { values[k] = Math.round(ddf * market * (0.7 + 0.6 * unit(p.key, k)) * 10) / 10; });
    map.set(String(p.key), {player_key: String(p.key), name: p.name, pos: p.pos, team: p.team || "", values});
  });
  return map;
}
const SHAPE = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0};
const ALLOCATION = [{pos: "QB", rostered: 30, lineup: 12, bench: 18}, {pos: "RB", rostered: 60, lineup: 36, bench: 24}, {pos: "WR", rostered: 66, lineup: 36, bench: 30}, {pos: "TE", rostered: 24, lineup: 12, bench: 12}];
const EXPECTED = F.expectedDepth(ALLOCATION, 12);
const WEIGHTS = {overall: 0.3, QB: 0.2, RB: 0.3, WR: 0.3, TE: 0.25};

const out = {pairs: 0, trades: 0, natural: 0, wouldBeNatural: 0, clearlyWorse: 0, failures: []};
const files = fs.readdirSync(fixDir).filter(f => /^fixture-.*\.json$/.test(f) && f !== "fixture-20team.json").sort();
for (const file of files) {
  const fx = JSON.parse(fs.readFileSync(path.join(fixDir, file), "utf8"));
  const rows = makeRows([].concat(...fx.teams.map(t => t.players)));
  const teams = fx.teams.map(t => F.withChartAverage(t.players.map(p => rows.get(String(p.key))).filter(Boolean), ANALYST));
  teams.forEach((mine, i) => teams.forEach((theirs, j) => {
    if (i === j || !mine.length || !theirs.length) return;
    out.pairs += 1;
    const res = F.findTrades(mine, theirs, {chartKeys: CH, maxSize: 2, limit: Infinity});
    const byKey = new Map(mine.concat(theirs).map(r => [String(r.player_key), r]));
    const wide = list => list.map(r => byKey.get(String(r.player_key)) || r);
    const ctx = {shape: SHAPE, expected: EXPECTED, weights: WEIGHTS, ourKey: "ddf_value", marketKey: "chart_avg", chartKeys: ANALYST, z: F.FIT_Z};
    res.trades.forEach(t => {
      const give = wide(t.give), recv = wide(t.receive);
      const fit = F.tradeFit({mine: {roster: mine, leaving: give, arriving: recv}, theirs: {roster: theirs, leaving: recv, arriving: give}}, ctx);
      if (!fit) return;
      out.trades += 1;
      const p = O.rosterImprovementPct({mine, theirs, give, receive: recv}, "partner",
        Object.assign({}, ctx, {senderKey: "ddf_value", partnerKey: "chart_avg"}));
      const n = fit.natural;
      if (fit.label === "natural") out.natural += 1;
      if (n.us.ok && n.them.value && n.them.construction && n.them.projections === true) out.wouldBeNatural += 1;
      if (p.band === "clearly_worse") out.clearlyWorse += 1;
      const id = `${file} ${i}->${j} ${give.map(r => r.player_key).join("+")} for ${recv.map(r => r.player_key).join("+")}`;
      if (fit.label === "natural" && p.band === "clearly_worse") out.failures.push(`${id}: Natural fit but the Why text says ${p.shown}%, clearly worse`);
      if (p.shown !== n.them.pct || p.band !== n.them.pctBand) out.failures.push(`${id}: Why ${p.shown}% ${p.band} vs fit ${n.them.pct}% ${n.them.pctBand}`);
    });
  }));
}
process.stdout.write(JSON.stringify(out));
