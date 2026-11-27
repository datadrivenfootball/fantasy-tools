/* Sample Cover data for ?mock=1 on localhost only (team-cover.js loads this file nowhere else). It uses the stored
 * team's own names with made-up weekly points, in the DDFWeekly.cover() shape. */
window.DDFStagingMockCover = function (summary) {
  "use strict";
  var team = (summary.teams || []).filter(function (t) { return t.team_key === summary.my_team_key; })[0] || {roster: []};
  var cur = summary.current_week || 13, weeks = [cur, cur + 1, cur + 2, cur + 3, cur + 4].filter(function (w) { return w <= 17; });
  var r1 = function (x) { return Math.round(x * 10) / 10; }, pos = function (p) { return p.position === "DST" ? "DEF" : p.position; };
  var by = {};
  team.roster.forEach(function (p) { (by[pos(p)] = by[pos(p)] || []).push(p); });
  var want = {QB: 1, RB: 2, WR: 3, TE: 1}, base = {QB: 19.5, RB: 14.2, WR: 13.1, TE: 9.4}, starters = [], n = 0;
  Object.keys(want).forEach(function (k) {
    (by[k] || []).slice(0, want[k]).forEach(function (p, i) {
      var backup = (by[k] || [])[want[k]] || null, row = {player_id: p.player_id, name: p.name, pos: k, slot: p.slot || k, status: p.status || null, weeks: {}, total_cost: 0, worst: null, kind: "ok", shared_with: []};
      n++;
      weeks.forEach(function (w, j) {
        var pts = r1(base[k] - i * 1.7 + ((n * 7 + j * 3) % 5) * 0.6), bye = n === 2 && j === 1, bench = n === 5 && j === 3, nul = n === 4 && j === 2;
        if (bye) { row.weeks[w] = {points: 0, starts: false, bye: true, cost: 0, cover: null}; return; }
        if (bench) { row.weeks[w] = {points: pts, starts: false, bye: false, cost: 0, cover: null}; return; }
        if (nul) { row.weeks[w] = {points: null, starts: true, bye: false, cost: null, cover: null, empty: false}; row.total_cost = null; return; }
        var share = k === "TE" ? 0.62 : k === "QB" ? 0.3 : i === 0 ? 0.42 : 0.16, c = r1(pts * share), empty = k === "TE" && !backup;
        if (empty) c = pts;
        row.weeks[w] = {points: pts, starts: true, bye: false, cost: c, cover: backup && !empty ? {player_id: backup.player_id, name: backup.name, points: r1(pts - c)} : null, empty: empty};
        if (row.total_cost !== null) row.total_cost = r1(row.total_cost + c);
        if (!row.worst || c > row.worst.cost) row.worst = {week: w, cost: c};
        if (empty || share >= 0.5) row.kind = "hole"; else if (row.kind !== "hole" && share >= 0.25) row.kind = "thin";
      });
      row._b = backup && backup.player_id;
      starters.push(row);
    });
  });
  starters.forEach(function (a) { starters.forEach(function (b) { if (a !== b && a._b && a._b === b._b) a.shared_with.push(b.player_id); }); });
  starters.forEach(function (a) { delete a._b; });
  var rank = {hole: 0, thin: 1, ok: 2};
  starters.sort(function (a, b) { return rank[a.kind] - rank[b.kind] || (b.total_cost || 0) - (a.total_cost || 0); });
  var kdef = ["K", "DEF"].map(function (k, i) {
    var mine = by[k] || [], cost = {}, sw = {}, add = {};
    weeks.forEach(function (w, j) { var bye = i === 0 && j === 0; sw[w] = {points: bye ? 0 : r1(8.1 - i + j * 0.3), bye: bye}; cost[w] = bye ? null : mine[0] ? sw[w].points : null; add[w] = i === 1 && j === 4 ? null : r1(7.2 - i * 0.4 + j * 0.2); });
    return {pos: k, starter: mine[0] ? {player_id: mine[0].player_id, name: mine[0].name} : null, backup: mine[1] ? {player_id: mine[1].player_id, name: mine[1].name} : null,
      best_add: {player_id: "mock-" + k, name: k === "K" ? "Sample Kicker" : "Sample Defense", weeks: add}, cost: cost, starter_weeks: mine[0] ? sw : null};
  });
  return {weeks: weeks, starters: starters, kdef: kdef, notes: ["Cost = your best lineup that week minus your best lineup without him, from weekly projections."]};
};
