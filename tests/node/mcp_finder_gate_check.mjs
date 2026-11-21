// Connector walkthrough 2026-11-21: find_trades_league returned 0 viable of 179 in a real 12-team league.
// Two causes, both fixed here, neither value math:
// 1. find-trades.ts called the site finder without minCharts, so the search used SEARCH_MIN_CHARTS = 1 (JEG-1403)
//    while the tool promises 3 of 4 charts; the pool filled with lopsided trades that the fairness check failed.
// 2. viability.ts deduplicateOffers kept the highest-edge offer per received set even when a viable one existed.
// Run by tests/test_mcp_remote.py.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { findTradesForPair, minChartsFor } from "../../supabase/functions/mcp/find-trades.ts";
import { deduplicateOffers } from "../../supabase/functions/mcp/viability.ts";

const finder = createRequire(import.meta.url)("../../app/v2/finder.js");
assert.equal(finder.MIN_CHARTS, 3);
assert.equal(minChartsFor(finder), 3, "all four charts priced: 3 of 4");
assert.equal(minChartsFor(finder, 4), 3);
assert.equal(minChartsFor(finder, 3), 2, "a chart on hold: 2 of 3");
assert.equal(minChartsFor(finder, 2), 1);
assert.equal(minChartsFor(finder, 0), 1);

// The finder gets the gate: a package only one chart calls fair for the rival is not a candidate.
const row = (player_key, name, pos, ddf, charts) => ({ player_key, name, pos,
  values: { [finder.OUR_KEY]: ddf, ...Object.fromEntries(finder.CHART_KEYS.map((k, i) => [k, charts[i]])) } });
// You give A (charts 10, 10, 10, 40) for B (charts 30 each): one chart has the rival even or ahead, three do not.
const mine = [row(1, "Give A", "WR", 20, [10, 10, 10, 40])];
const theirs = [row(2, "Get B", "WR", 40, [30, 30, 30, 30])];
const asked = [];
const spy = { ...finder, findTrades: (m, t, o) => { asked.push(o.minCharts); return finder.findTrades(m, t, o); } };
let r = findTradesForPair(spy, mine, theirs, { maxSize: 1, limit: 10 });
assert.deepEqual(asked, [3]);
assert.equal(r.trades.length, 0, "1 of 4 charts fair to the rival is not a candidate");
const fair = [row(1, "Give A", "WR", 20, [40, 40, 40, 10])];
const theirsFair = [row(2, "Get B", "WR", 40, [30, 30, 30, 30])];
r = findTradesForPair(finder, fair, theirsFair, { maxSize: 1, limit: 10 });
assert.equal(r.trades.length, 1, "3 of 4 charts fair to the rival is a candidate");

// Dedupe keeps the viable package over a higher-edge one that fails a check.
const offer = (id, viable, failed, ddfEdge) => ({ id, viable, ddfEdge, userGets: [{ player_key: 9 }, { player_key: 8 }],
  checks: [...Array(9)].map((_, i) => ({ passed: i >= failed })) });
const kept = deduplicateOffers([offer("lopsided", false, 2, 30), offer("viable", true, 0, 12), offer("close", false, 1, 20)]);
assert.deepEqual(kept.map((o) => o.id), ["viable"]);
assert.deepEqual(deduplicateOffers([offer("two", false, 2, 30), offer("one", false, 1, 5)]).map((o) => o.id), ["one"]);
assert.deepEqual(deduplicateOffers([offer("lo", true, 0, 5), offer("hi", true, 0, 9)]).map((o) => o.id), ["hi"]);
console.log("ok");
