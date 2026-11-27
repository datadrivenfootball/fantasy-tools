/* EDDF (JEG-1735): the enhanced DDF Value, JS twin of pipelines/eddf.py.
   Off by default and not wired into the engine: value-model.js and curve-widget.js do not
   call it until the hot-file slot is free and Jeremy approves the wiring. Pure functions.
   tests/test_eddf.py runs this file against tests/fixtures/eddf_parity.json (written by the
   Python module) so the two cannot drift. */
(function (root) {
  "use strict";

  function isotonicNonincreasing(xs, ys) {
    if (!xs.length) throw new Error("no anchors");
    var pts = xs.map(function (x, i) { return [x, ys[i]]; }).sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    var groups = [];
    pts.forEach(function (p) {
      var g = groups[groups.length - 1];
      if (g && g[0] === p[0]) { g[1] += p[1]; g[2] += 1; } else groups.push([p[0], p[1], 1]);
    });
    var blocks = [];
    groups.forEach(function (g) {
      blocks.push([g[0], g[0], g[1], g[2]]);
      while (blocks.length > 1) {
        var a = blocks[blocks.length - 2], b = blocks[blocks.length - 1];
        if (!(a[2] / a[3] < b[2] / b[3])) break;
        blocks.splice(blocks.length - 2, 2, [a[0], b[1], a[2] + b[2], a[3] + b[3]]);
      }
    });
    var knots = [];
    blocks.forEach(function (b) {
      var m = b[2] / b[3];
      knots.push([b[0], m]);
      if (b[1] !== b[0]) knots.push([b[1], m]);
    });
    return function (x) {
      if (x <= knots[0][0]) return knots[0][1];
      if (x >= knots[knots.length - 1][0]) return knots[knots.length - 1][1];
      for (var i = 0; i + 1 < knots.length; i++) {
        var k0 = knots[i], k1 = knots[i + 1];
        if (k0[0] <= x && x <= k1[0]) return k1[0] === k0[0] ? k0[1] : k0[1] + (k1[1] - k0[1]) * (x - k0[0]) / (k1[0] - k0[0]);
      }
      return knots[knots.length - 1][1];
    };
  }

  function stableAnchors(history, stability, floorFrac) {
    var out = {};
    if (!history.length) return out;
    var top = 0;
    history.forEach(function (h) { Object.keys(h).forEach(function (k) { if (h[k] > top) top = h[k]; }); });
    var floor = floorFrac * top;
    Object.keys(history[0]).forEach(function (pk) {
      var vs = history.map(function (h) { return h[pk]; });
      if (vs.some(function (v) { return v === undefined || v === null; })) return;
      var mean = vs.reduce(function (a, b) { return a + b; }, 0) / vs.length;
      if (Math.max.apply(null, vs) - Math.min.apply(null, vs) <= stability * Math.max(mean, floor)) out[pk] = vs[0];
    });
    return out;
  }

  function impliedValues(ranks, anchors, posOf, cfg) {
    var excl = cfg.exclude_positions, xs = [], ys = [];
    Object.keys(anchors).forEach(function (pk) {
      if (ranks[pk] !== undefined && excl.indexOf(posOf[pk]) < 0) { xs.push(ranks[pk]); ys.push(anchors[pk]); }
    });
    if (xs.length < cfg.min_anchors) return {};
    var f = isotonicNonincreasing(xs, ys), out = {};
    Object.keys(ranks).forEach(function (pk) { if (excl.indexOf(posOf[pk]) < 0) out[pk] = f(ranks[pk]); });
    return out;
  }

  function dayNumber(iso) { return Math.floor(Date.parse(iso + "T00:00:00Z") / 86400000); }

  // Monday = 0, as in Python's date.weekday(); 1970-01-01 was a Thursday (3).
  function weekdayOf(iso) { return (dayNumber(iso) + 3) % 7; }

  function rankerStatus(ranker, vintage, asOf, staleDays, scoring, resetWeekday) {
    if (ranker.enabled === false) return { id: ranker.id, in: false };
    if (ranker.scoring.indexOf(scoring) < 0) return { id: ranker.id, in: false };
    if (vintage === null || vintage === undefined) return { id: ranker.id, in: false };
    if (resetWeekday !== null && resetWeekday !== undefined) {
      var reset = dayNumber(asOf) - ((weekdayOf(asOf) - resetWeekday + 7) % 7);
      if (dayNumber(vintage) < reset) return { id: ranker.id, in: false };
    }
    return { id: ranker.id, in: dayNumber(asOf) - dayNumber(vintage) <= staleDays };
  }

  /* chartAdjusted {chart: {pk: v}}, lists {rankerId: {pk: rank}}, vintages {rankerId: 'YYYY-MM-DD'},
     anchorHistory [{pk: v}] newest first, posOf {pk: pos}. Returns {values: {pk: {value, count, sources}}, rankers}. */
  function eddf(chartAdjusted, lists, vintages, anchorHistory, posOf, cfg, asOf, scoring) {
    var anchors = stableAnchors(anchorHistory, cfg.anchor_stability, cfg.anchor_floor_frac);
    var implied = {}, status = [];
    cfg.rankers.forEach(function (r) {
      var st = rankerStatus(r, vintages[r.id], asOf, cfg.stale_days, scoring, cfg.stale_weekday);
      if (st.in) {
        var vals = impliedValues(lists[r.id] || {}, anchors, posOf, cfg);
        if (!Object.keys(vals).length) st = { id: r.id, in: false }; else implied[r.id] = vals;
      }
      status.push(st);
    });
    var values = {};
    Object.keys(posOf).forEach(function (pk) {
      var parts = {};
      Object.keys(chartAdjusted).forEach(function (c) { var v = chartAdjusted[c][pk]; if (v !== undefined && v !== null) parts[c] = v; });
      Object.keys(implied).forEach(function (rid) { if (implied[rid][pk] !== undefined) parts[rid] = implied[rid][pk]; });
      var keys = Object.keys(parts).sort();
      if (keys.length) values[pk] = { value: keys.reduce(function (a, k) { return a + parts[k]; }, 0) / keys.length, count: keys.length, sources: keys };
    });
    return { values: values, rankers: status };
  }

  var api = { isotonicNonincreasing: isotonicNonincreasing, stableAnchors: stableAnchors, impliedValues: impliedValues, eddf: eddf };
  root.EddfModel = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
