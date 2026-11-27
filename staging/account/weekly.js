/* DDF weekly planner (JEG-1736, staging). Pure: no DOM, no network. Loaded by the staging pages and by deno test.
 * Weekly scoring only (Jeremy, 2026-11-27, revision 3): each side's best legal lineup from weekly projections, a win
 * chance from the projected margin plus a weekly spread, Yahoo's number beside it. DDF Value is never read here.
 * Missing is never 0: a player with no projection is listed as unscored with its reason; a team week whose lineup
 * cannot be scored from real data is null.
 *
 * globalThis.DDFWeekly:
 *   plan(summary, weekly, opts)            -> the Games left planner (docs/signed-in-features.md)
 *   slotsOf(summary)                       -> starter slots, e.g. ["QB","WR","WR","WR","RB","RB","TE","W/R/T","K","DEF"]
 *   lineup(slots, players)                 -> best legal lineup for one team week
 *   teamWeek(summary, weekly, roster, week)-> Lineup for a roster (array of snapshot roster entries) in one week
 *   winChance(margin, sd)                  -> P(win) for a projected margin and one team's weekly sd
 *   fitSpread(summary)                     -> {sd, basis, n}
 */
(function (root) {
  "use strict";
  var ELIGIBLE = {
    QB: ["QB"], RB: ["RB"], WR: ["WR"], TE: ["TE"], K: ["K"], DEF: ["DEF"], "D/ST": ["DEF"], DST: ["DEF"],
    "W/R/T": ["RB", "WR", "TE"], FLEX: ["RB", "WR", "TE"],
    "W/R": ["RB", "WR"], "RB/WR": ["RB", "WR"], WRRB_FLEX: ["RB", "WR"],
    "W/T": ["WR", "TE"], "WR/TE": ["WR", "TE"], REC_FLEX: ["WR", "TE"],
    "Q/W/R/T": ["QB", "RB", "WR", "TE"], OP: ["QB", "RB", "WR", "TE"], SUPER_FLEX: ["QB", "RB", "WR", "TE"]
  };
  var DEFAULT_SD = 22; // one team's weekly sd when the league gives too few Yahoo matchups to fit it
  var GOALS = [
    {id: "high_score", label: "Weekly high score"},
    {id: "record", label: "Best regular-season record"},
    {id: "seed", label: "Playoff seed"},
    {id: "playoffs", label: "Win the playoffs"}
  ];

  function num(x) { return typeof x === "number" && isFinite(x) ? x : null; }
  function r1(x) { return x === null ? null : Math.round(x * 10) / 10; }
  function r3(x) { return x === null ? null : Math.round(x * 1000) / 1000; }
  function posOf(p) { var s = String((p && p.position) || "").toUpperCase(); return s === "DST" || s === "D/ST" ? "DEF" : s; }
  function ord(n) { var s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function rec(t) { var s = t.wins + "-" + t.losses; return t.ties ? s + "-" + t.ties : s; }

  // ---------- normal distribution ----------
  function phi(z) { // standard normal cdf (Abramowitz-Stegun 7.1.26, error < 1.5e-7)
    var t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2);
    var y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z / 2);
    return z >= 0 ? (1 + y) / 2 : (1 - y) / 2;
  }
  function phiInv(p) { // Acklam's rational approximation
    var a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
    var b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
    var c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
    var d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
    var q, r;
    if (p < 0.02425) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    if (p > 1 - 0.02425) { q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    q = p - 0.5; r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }
  function winChance(margin, sd) { return margin === null ? null : phi(margin / (sd * Math.SQRT2)); }
  function rng(seed) { // mulberry32
    var s = seed >>> 0;
    return function () { s += 0x6D2B79F5; var t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function gauss(rand) { var u = 1 - rand(), v = rand(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }

  // The weekly spread, fitted from Yahoo's own projections and win probabilities in this league (unplayed games):
  // p = phi(margin / (sd * sqrt 2)), so sd = margin / (sqrt 2 * phiInv(p)). Median over matchups.
  function fitSpread(summary) {
    var est = [];
    (summary.schedule || []).forEach(function (w) {
      (w.matchups || []).forEach(function (m) {
        var pp = m.projected_points || [], wp = m.win_probability || [];
        if (m.status === "final" || num(pp[0]) === null || num(pp[1]) === null || num(wp[0]) === null) return;
        var p = wp[0], margin = pp[0] - pp[1];
        if (p <= 0.03 || p >= 0.97 || Math.abs(p - 0.5) < 0.04 || Math.abs(margin) < 2) return;
        var z = phiInv(p);
        if (z * margin <= 0) return; // Yahoo's favourite is not the projection's favourite: no information on sd
        est.push(margin / (Math.SQRT2 * z));
      });
    });
    if (est.length < 3) return {sd: DEFAULT_SD, basis: "default " + DEFAULT_SD + " points (too few Yahoo matchups to fit)", n: est.length};
    est.sort(function (a, b) { return a - b; });
    var sd = est[Math.floor(est.length / 2)];
    sd = Math.max(12, Math.min(40, sd));
    return {sd: r1(sd), basis: "fitted from Yahoo's projections and win chances in " + est.length + " matchups", n: est.length};
  }

  // ---------- lineups ----------
  function slotsOf(summary) {
    var st = summary.settings || {};
    var rp = (st.roster_positions || []).filter(function (s) { return ELIGIBLE[s]; });
    if (rp.length) return rp;
    var r = (st.ddf && st.ddf.roster) || {QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, K: 1, DST: 1}, out = [];
    ["QB", "RB", "WR", "TE"].forEach(function (p) { for (var i = 0; i < (r[p] || 0); i++) out.push(p); });
    for (var i = 0; i < (r.FLEX || 0); i++) out.push("W/R/T");
    if (st.ddf && st.ddf.superflex) for (var j = 0; j < (st.ddf.superflexSlots || 1); j++) out.push("Q/W/R/T");
    for (var k = 0; k < (r.K || 0); k++) out.push("K");
    for (var l = 0; l < (r.DST || 0); l++) out.push("DEF");
    return out;
  }
  function canFill(p, slot) {
    var el = ELIGIBLE[slot] || [];
    return el.indexOf(p.pos) >= 0;
  }
  // Dedicated slots first, then narrow flex, then wide: flex sets nest on every platform DDF reads, so greedy by
  // points within that order is the best legal lineup.
  function slotOrder(slots) {
    return slots.map(function (s, i) { return {slot: s, i: i, w: (ELIGIBLE[s] || []).length}; })
      .sort(function (a, b) { return a.w - b.w || a.i - b.i; });
  }
  function lineup(slots, players) {
    // a player on bye cannot start: he sits on the bench as BYE, and a slot nobody else can fill is empty (a real 0)
    var real = players.filter(function (p) { return p.points !== null && !p.bye; })
      .sort(function (a, b) { return b.points - a.points || (a.player_id < b.player_id ? -1 : 1); });
    var missing = players.filter(function (p) { return p.points === null; });
    var used = {}, starters = new Array(slots.length), empty = [];
    slotOrder(slots).forEach(function (o) {
      var pick = real.filter(function (p) { return !used[p.player_id] && canFill(p, o.slot); })[0];
      if (pick) { used[pick.player_id] = true; starters[o.i] = Object.assign({slot: o.slot}, pick); }
      else { empty.push(o.slot); starters[o.i] = {slot: o.slot, player_id: null, name: null, pos: null, points: null, note: "Empty"}; }
    });
    // A slot left empty by byes and outs is a real 0. One a missing player could have filled is missing data.
    var blocked = empty.filter(function (s) { return missing.some(function (p) { return canFill(p, s); }); });
    var total = blocked.length ? null : starters.reduce(function (t, s) { return t + (s.points || 0); }, 0);
    return {
      total: total === null ? null : r1(total),
      starters: starters,
      bench: real.filter(function (p) { return !used[p.player_id]; }).concat(players.filter(function (p) { return p.bye; })),
      empty_slots: empty,
      unscored: missing.map(function (p) { return {player_id: p.player_id, name: p.name, pos: p.pos, reason: p.note || "No projection"}; }),
      reason: blocked.length ? "No projection for a player who would start at " + blocked.join(", ") : null
    };
  }
  function playerWeek(weekly, entry, week) {
    var w = weekly.players[entry.player_id] || {};
    var c = (w.weeks || {})[String(week)] || null;
    var pos = posOf(entry);
    return {
      player_id: entry.player_id, name: entry.name, pos: pos, nfl_team: entry.nfl_team || null,
      points: c ? num(c.points) : null, source: c ? c.source : null, status: entry.status || null,
      bye: !!(c && c.bye), note: c ? c.note : (weekly.players[entry.player_id] ? "No projection this week" : "Not in the weekly read"),
      slot_now: entry.slot || null, match: w.match || null
    };
  }
  function teamWeek(summary, weekly, roster, week, slots) {
    slots = slots || slotsOf(summary);
    return lineup(slots, (roster || []).map(function (e) { return playerWeek(weekly, e, week); }));
  }

  // ---------- season simulation (regular season, then the bracket) ----------
  function bracketPlan(spots) {
    // first-round pairings by seed, and how the next rounds fill; Yahoo does not reseed.
    if (spots === 2) return {byes: 0, rounds: [[[1, 2]]]};
    if (spots === 4) return {byes: 0, rounds: [[[1, 4], [2, 3]], [["w0", "w1"]]]};
    if (spots === 6) return {byes: 2, rounds: [[[3, 6], [4, 5]], [[1, "w1"], [2, "w0"]], [["w0", "w1"]]]};
    if (spots === 8) return {byes: 0, rounds: [[[1, 8], [4, 5], [2, 7], [3, 6]], [["w0", "w1"], ["w2", "w3"]], [["w0", "w1"]]]};
    return null;
  }

  function plan(summary, weekly, opts) {
    opts = opts || {};
    var RUNS = opts.runs || 10000;
    var rand = rng(opts.seed || 1736);
    var st = summary.settings || {};
    var teams = summary.teams || [];
    var meKey = opts.myTeamKey || summary.my_team_key;
    var me = teams.filter(function (t) { return t.team_key === meKey; })[0];
    if (!me) throw new Error("Pick your team first.");
    var slots = slotsOf(summary);
    var spread = fitSpread(summary);
    var sd = spread.sd;
    var cur = num(summary.current_week) || (weekly.weeks || [])[0] || 1;
    var lastReg = num(st.last_regular_week) || (num(st.playoff_start_week) ? st.playoff_start_week - 1 : null);
    var spots = num(st.playoff_teams);
    var bp = spots ? bracketPlan(spots) : null;
    var weeks = (weekly.weeks || []).filter(function (w) { return w >= cur; });
    var regWeeks = weeks.filter(function (w) { return lastReg === null || w <= lastReg; });
    var poWeeks = weeks.filter(function (w) { return lastReg !== null && w > lastReg; });
    var name = {}; teams.forEach(function (t) { name[t.team_key] = t.name; });
    var stand = {}; teams.forEach(function (t) {
      var s = t.standings || {};
      stand[t.team_key] = {wins: s.wins || 0, losses: s.losses || 0, ties: s.ties || 0, pf: num(s.points_for) || 0, rank: num(s.rank)};
    });

    // every team's best lineup, every week
    var tw = {}; // tw[team][week] = Lineup
    teams.forEach(function (t) { tw[t.team_key] = {}; weeks.forEach(function (w) { tw[t.team_key][w] = teamWeek(summary, weekly, t.roster, w, slots); }); });
    function proj(teamKey, w, m) { // a team week's mean: DDF's lineup, else Yahoo's projection (named in sources)
      var l = tw[teamKey] && tw[teamKey][w];
      if (l && l.total !== null) return l.total;
      if (m) { var i = m.team_keys.indexOf(teamKey), y = num((m.projected_points || [])[i]); if (y !== null) return y; }
      return null;
    }
    var sched = {}; (summary.schedule || []).forEach(function (w) { sched[w.week] = w.matchups || []; });
    var regGames = []; // [{week, a, b, ma, mb}]
    regWeeks.forEach(function (w) {
      (sched[w] || []).forEach(function (m) {
        if (m.status === "final" || !m.team_keys || m.team_keys.length !== 2) return;
        regGames.push({week: w, a: m.team_keys[0], b: m.team_keys[1], ma: proj(m.team_keys[0], w, m), mb: proj(m.team_keys[1], w, m)});
      });
    });
    var weekMean = {}; weeks.forEach(function (w) {
      var xs = teams.map(function (t) { return proj(t.team_key, w); }).filter(function (x) { return x !== null; });
      weekMean[w] = xs.length ? xs.reduce(function (a, b) { return a + b; }, 0) / xs.length : null;
    });

    var keys = teams.map(function (t) { return t.team_key; });
    var myGames = regGames.filter(function (g) { return g.a === meKey || g.b === meKey; });
    var acc = {playoff: 0, top: 0, bye: 0, title: 0, seedSum: 0, n: 0};
    var seedCount = {}; keys.forEach(function (k) { seedCount[k] = new Array(teams.length + 1).fill(0); });
    var byWins = {}; // my final wins -> {n, playoff, bye}
    var byGame = myGames.map(function () { return {win: {n: 0, playoff: 0, bye: 0, top: 0}, loss: {n: 0, playoff: 0, bye: 0, top: 0}}; });
    var hsWins = {}; weeks.forEach(function (w) { hsWins[w] = 0; });
    var poOpp = {}; poWeeks.forEach(function (w) { poOpp[w] = {}; });
    var poAlive = {}; poWeeks.forEach(function (w) { poAlive[w] = 0; });
    var poWin = {}; poWeeks.forEach(function (w) { poWin[w] = 0; });
    var titleBy = {}; keys.forEach(function (k) { titleBy[k] = 0; });

    for (var run = 0; run < RUNS; run++) {
      var W = {}, PF = {};
      keys.forEach(function (k) { W[k] = stand[k].wins + stand[k].ties / 2; PF[k] = stand[k].pf; });
      var score = {}; // score[w][team]
      weeks.forEach(function (w) {
        score[w] = {};
        keys.forEach(function (k) {
          var mu = proj(k, w); if (mu === null) mu = weekMean[w];
          score[w][k] = mu === null ? null : mu + sd * gauss(rand);
        });
        var best = null, bk = null;
        keys.forEach(function (k) { if (score[w][k] !== null && (best === null || score[w][k] > best)) { best = score[w][k]; bk = k; } });
        if (bk === meKey) hsWins[w]++;
      });
      var myResults = [];
      regGames.forEach(function (g) {
        var sa = g.ma === null ? score[g.week][g.a] : g.ma + (score[g.week][g.a] - (proj(g.a, g.week) === null ? weekMean[g.week] : proj(g.a, g.week)));
        var sb = g.mb === null ? score[g.week][g.b] : g.mb + (score[g.week][g.b] - (proj(g.b, g.week) === null ? weekMean[g.week] : proj(g.b, g.week)));
        if (sa === null || sb === null) { if (g.a === meKey || g.b === meKey) myResults.push(null); return; }
        PF[g.a] += sa; PF[g.b] += sb;
        var aw = sa > sb;
        W[aw ? g.a : g.b] += 1;
        if (g.a === meKey || g.b === meKey) myResults.push((g.a === meKey) === aw);
      });
      var order = keys.slice().sort(function (x, y) { return W[y] - W[x] || PF[y] - PF[x]; });
      var seed = {}; order.forEach(function (k, i) { seed[k] = i + 1; seedCount[k][i + 1]++; });
      var mySeed = seed[meKey], inPo = spots ? mySeed <= spots : false, hasBye = bp && bp.byes ? mySeed <= bp.byes : false;
      acc.n++; acc.seedSum += mySeed; if (inPo) acc.playoff++; if (mySeed === 1) acc.top++; if (hasBye) acc.bye++;
      var fw = W[meKey] - stand[meKey].ties / 2;
      byWins[fw] = byWins[fw] || {n: 0, playoff: 0, bye: 0};
      byWins[fw].n++; if (inPo) byWins[fw].playoff++; if (hasBye) byWins[fw].bye++;
      myResults.forEach(function (won, i) { if (won === null) return; var b = byGame[i][won ? "win" : "loss"]; b.n++; if (inPo) b.playoff++; if (hasBye) b.bye++; if (mySeed === 1) b.top++; });
      // the bracket, one round per playoff week
      if (bp && poWeeks.length >= bp.rounds.length) {
        var bySeed = {}; order.forEach(function (k, i) { bySeed[i + 1] = k; });
        var prev = [];
        bp.rounds.forEach(function (round, ri) {
          var w = poWeeks[ri], next = [];
          round.forEach(function (pair) {
            var a = typeof pair[0] === "string" ? prev[+pair[0].slice(1)] : bySeed[pair[0]];
            var b = typeof pair[1] === "string" ? prev[+pair[1].slice(1)] : bySeed[pair[1]];
            var sa = score[w][a], sb = score[w][b];
            var win = sa === null || sb === null ? (rand() < 0.5 ? a : b) : sa > sb ? a : b;
            if (a === meKey || b === meKey) {
              var o = a === meKey ? b : a;
              poOpp[w][o] = (poOpp[w][o] || 0) + 1; poAlive[w]++;
              if (win === meKey) poWin[w]++;
            }
            next.push(win);
          });
          prev = next;
        });
        titleBy[prev[0]]++;
        if (prev[0] === meKey) acc.title++;
      }
    }
    var P = function (x) { return r3(x / acc.n); };
    var simOut = {
      runs: acc.n, playoff_p: spots ? P(acc.playoff) : null, top_seed_p: P(acc.top), bye_p: bp && bp.byes ? P(acc.bye) : null,
      title_p: bp ? P(acc.title) : null, expected_seed: r1(acc.seedSum / acc.n),
      by_final_wins: Object.keys(byWins).map(Number).sort(function (a, b) { return a - b; }).map(function (w) {
        var b = byWins[w]; return {wins: w, p_reach: P(b.n), playoff_p: r3(b.playoff / b.n), bye_p: bp && bp.byes ? r3(b.bye / b.n) : null};
      })
    };
    var fw0 = stand[meKey].wins;
    var clinch = simOut.by_final_wins.filter(function (b) { return b.playoff_p === 1 && b.p_reach >= 0.001; })[0];
    var safe = simOut.by_final_wins.filter(function (b) { return b.playoff_p >= 0.95 && b.p_reach >= 0.001; })[0];
    simOut.clinch_wins = clinch ? clinch.wins : null;
    simOut.safe_wins = safe ? safe.wins : null;

    // ---------- the games ----------
    var gamesOut = [];
    var myWinP = [];
    weeks.forEach(function (w) {
      var phase = poWeeks.indexOf(w) >= 0 ? "playoffs" : "regular";
      var m = (sched[w] || []).filter(function (x) { return x.team_keys && x.team_keys.indexOf(meKey) >= 0; })[0] || null;
      var oppKey = m ? m.team_keys[1 - m.team_keys.indexOf(meKey)] : null;
      var i = m ? m.team_keys.indexOf(meKey) : -1;
      var mine = Object.assign({team_key: meKey, name: me.name}, tw[meKey][w]);
      var theirs = oppKey ? Object.assign({team_key: oppKey, name: name[oppKey]}, tw[oppKey][w]) : null;
      var margin = theirs && mine.total !== null && theirs.total !== null ? r1(mine.total - theirs.total) : null;
      var ddf = margin === null ? null : r3(winChance(margin, sd));
      var yahoo = m && num((m.win_probability || [])[i]) !== null ? m.win_probability[i] : null;
      var yp = m && num((m.projected_points || [])[i]) !== null ? {mine: m.projected_points[i], theirs: num(m.projected_points[1 - i])} : null;
      var totals = keys.map(function (k) { return {k: k, t: proj(k, w)}; }).filter(function (x) { return x.t !== null; }).sort(function (a, b) { return b.t - a.t; });
      var myRank = totals.map(function (x) { return x.k; }).indexOf(meKey) + 1;
      var topOther = totals.filter(function (x) { return x.k !== meKey; })[0];
      var g = {
        week: w, phase: phase, status: m ? m.status : null,
        opp: oppKey ? {team_key: oppKey, name: name[oppKey], wins: stand[oppKey].wins, losses: stand[oppKey].losses, ties: stand[oppKey].ties, rank: stand[oppKey].rank, playoff_p: spots ? r3(seedCount[oppKey].slice(1, spots + 1).reduce(function (a, b) { return a + b; }, 0) / acc.n) : null} : null,
        opp_note: null, likely: null,
        mine: mine, theirs: theirs, margin: margin,
        win: {ddf: ddf, yahoo: yahoo}, yahoo_proj: yp,
        high_score: {chance: r3(hsWins[w] / acc.n), my_rank: myRank || null, of: totals.length, top: topOther ? {name: name[topOther.k], total: r1(topOther.t)} : null},
        stake: {playoffs: null, seed: null}, type: phase === "playoffs" ? "playoff" : null, goals: [], moves: []
      };
      if (phase === "playoffs" && !oppKey) {
        var alive = poAlive[w] || 0;
        g.opp_note = alive ? "Set by the bracket. You reach this game in " + Math.round(100 * alive / acc.n) + "% of runs." : "Set by the bracket. You do not reach this game in the simulation.";
        g.likely = Object.keys(poOpp[w] || {}).map(function (k) { return {team_key: k, name: name[k], p: r3(poOpp[w][k] / Math.max(1, alive)), total: r1(proj(k, w))}; })
          .sort(function (a, b) { return b.p - a.p; }).slice(0, 3);
        if (alive) g.win.ddf = r3(poWin[w] / alive);
        if (g.likely.length && g.likely[0].total !== null && mine.total !== null) g.margin = r1(mine.total - g.likely[0].total);
      }
      var gi = myGames.map(function (x) { return x.week; }).indexOf(w);
      if (gi >= 0) {
        var bw = byGame[gi].win, bl = byGame[gi].loss;
        var rate = function (b, k) { return b.n ? b[k] / b.n : null; };
        var sp = rate(bw, "playoff") !== null && rate(bl, "playoff") !== null ? r3(rate(bw, "playoff") - rate(bl, "playoff")) : null;
        var key2 = bp && bp.byes ? "bye" : "top";
        var ss = rate(bw, key2) !== null && rate(bl, key2) !== null ? r3(rate(bw, key2) - rate(bl, key2)) : null;
        var tp = rate(bw, "top") !== null && rate(bl, "top") !== null ? rate(bw, "top") - rate(bl, "top") : null;
        g.stake = {playoffs: spots ? sp : null, seed: ss, top_seed: tp === null ? null : r3(tp), seed_basis: key2 === "bye" ? "first-round bye" : "1st seed"};
        var p = g.win.ddf;
        var s1 = Math.abs(sp || 0), s2 = Math.abs(ss || 0);
        // framework §3b: free = stake about 0; seed game = moves the seed more than the odds of getting in;
        // bankable = 75%+ or a low stake; must-win = high stake and 35-65%; favored 65-75%; uphill under 35%
        g.type = s1 < 0.02 && s2 < 0.02 ? "free" : s2 > s1 && s2 >= 0.05 ? "seed_game"
          : (p !== null && p >= 0.75) || s1 < 0.05 ? "bankable" : p === null ? "must_win" : p > 0.65 ? "favored" : p < 0.35 ? "uphill" : "must_win";
        myWinP.push(p);
      }
      if (g.high_score.chance >= 0.08) g.goals.push("high_score");
      if (phase === "regular" && g.stake.top_seed !== null && Math.abs(g.stake.top_seed) >= 0.02) g.goals.push("record");
      if (phase === "regular" && g.stake.seed !== null && Math.abs(g.stake.seed) >= 0.02) g.goals.push("seed");
      if (phase === "playoffs" || (g.stake.playoffs !== null && Math.abs(g.stake.playoffs) >= 0.02)) g.goals.push("playoffs");
      g.moves = movesFor(summary, weekly, me, w, slots, mine, cur, m);
      gamesOut.push(g);
    });

    // wins distribution over the remaining regular-season games (independent games, DDF win chances)
    var dist = [1];
    myWinP.forEach(function (p) {
      if (p === null) return;
      var nx = new Array(dist.length + 1).fill(0);
      dist.forEach(function (v, k) { nx[k] += v * (1 - p); nx[k + 1] += v * p; });
      dist = nx;
    });
    var counted = myWinP.filter(function (p) { return p !== null; }).length;
    var winsOut = {dist: dist.map(function (p, k) { return {wins: k, p: r3(p)}; }).reverse(), expected: r1(dist.reduce(function (a, p, k) { return a + p * k; }, 0)), games: counted};

    // header sentences
    var s0 = stand[meKey], need = [];
    var left = myGames.length;
    need.push(rec(s0) + ", " + (s0.rank ? ord(s0.rank) : "rank unknown") + ". " + (left ? left + " regular-season game" + (left === 1 ? "" : "s") + " left." : "Regular season done."));
    if (spots) {
      if (simOut.playoff_p === 1) need.push("You are in the playoffs in every run.");
      else if (simOut.playoff_p === 0) need.push("You miss the playoffs in every run. The weekly high score is still live.");
      else {
        var c = simOut.clinch_wins, sf = simOut.safe_wins;
        if (c !== null) need.push("Win " + Math.max(0, c - fw0) + " more and you are in whatever else happens" + (sf !== null && sf < c ? "; win " + Math.max(0, sf - fw0) + " and you are in " + Math.round(100 * (simOut.by_final_wins.filter(function (b) { return b.wins === sf; })[0].playoff_p)) + "% of runs." : "."));
        else if (sf !== null) need.push("Win " + Math.max(0, sf - fw0) + " more and you are in at least 95% of runs.");
        need.push("Playoff chance now: " + Math.round(100 * simOut.playoff_p) + "%.");
      }
      if (bp && bp.byes && simOut.bye_p !== null && simOut.bye_p > 0 && simOut.bye_p < 1) {
        var byeAt = simOut.by_final_wins.filter(function (b) { return b.bye_p !== null && b.bye_p >= 0.5; })[0];
        if (byeAt) need.push("Win " + Math.max(0, byeAt.wins - fw0) + " for a first-round bye in most runs (" + Math.round(100 * simOut.bye_p) + "% now).");
      }
    }

    var hsExpected = gamesOut.filter(function (g) { return g.phase === "regular"; }).reduce(function (a, g) { return a + (g.high_score.chance || 0); }, 0);
    var goals = GOALS.map(function (g) {
      var detail = g.id === "high_score" ? "Expected weekly high scores left: " + hsExpected.toFixed(1) + (/USO/i.test(summary.name || "") ? " (USO pays $50 a week)" : "")
        : g.id === "record" ? "Best record in " + Math.round(100 * simOut.top_seed_p) + "% of runs"
        : g.id === "seed" ? "Expected seed " + simOut.expected_seed + (simOut.bye_p !== null ? "; bye in " + Math.round(100 * simOut.bye_p) + "%" : "")
        : simOut.title_p !== null ? "Playoffs in " + Math.round(100 * (simOut.playoff_p || 0)) + "%; title in " + Math.round(100 * simOut.title_p) + "%" : "Playoff format not in the data";
      return {id: g.id, label: g.label, detail: detail};
    });

    var standings = teams.map(function (t) {
      var s = stand[t.team_key], sc = seedCount[t.team_key];
      return {team_key: t.team_key, name: t.name, wins: s.wins, losses: s.losses, ties: s.ties, rank: s.rank, points_for: s.pf,
        playoff_p: spots ? r3(sc.slice(1, spots + 1).reduce(function (a, b) { return a + b; }, 0) / acc.n) : null,
        title_p: bp ? r3(titleBy[t.team_key] / acc.n) : null,
        seed_p: sc.slice(1).map(function (x) { return r3(x / acc.n); })};
    }).sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); });

    var sources = [], missing = [];
    var src = weekly.as_of || {};
    sources.push("Player projections: ESPN weekly" + (src.espn ? " (as of " + src.espn.slice(0, 16).replace("T", " ") + " UTC)" : "") + ", Sleeper where ESPN has no row.");
    sources.push("K and DEF: ESPN weekly projections, read live" + (src.kdef ? " " + src.kdef.slice(0, 16).replace("T", " ") + " UTC" : "") + ".");
    sources.push("Win chance: DDF, from both best lineups and a weekly spread of " + sd + " points per team (" + spread.basis + "). Yahoo's number is shown beside it.");
    sources.push("Season and bracket: " + acc.n.toLocaleString("en-US") + " simulated runs, games independent; tiebreak points for.");
    if (summary.source && summary.source.kind === "flaim") sources.push("League data via Flaim (stand-in until Yahoo is approved).");
    (weekly.unmatched || []).forEach(function (u) { missing.push({what: u.name, reason: u.reason}); });
    var byTeam = 0;
    Object.keys(weekly.players || {}).forEach(function (id) {
      var p = weekly.players[id];
      if (p.match === "team" || p.match === "team_name") byTeam++;
      else if (p.match === "name") missing.push({what: p.name, reason: "Matched to ESPN by name only; ESPN files him " + ((p.weeks && Object.keys(p.weeks).map(function (w) { return p.weeks[w].note; }).filter(Boolean)[0]) || "under another team").replace(/^ESPN lists him /, "") + ""});
    });
    if (byTeam) missing.push({what: "Kickers and defenses", reason: byTeam + " matched to ESPN by NFL team (no id is shared across platforms for K and DEF)"});
    if (!spots) missing.push({what: "Playoff format", reason: "Playoff teams not in the league data"});

    return {
      league: {name: summary.name, season: summary.season, current_week: cur, last_regular_week: lastReg, playoff_start_week: num(st.playoff_start_week), playoff_teams: spots,
        num_teams: teams.length, trade_deadline: st.trade_deadline || null, scoring: (st.ddf && st.ddf.scoring) || null, pulled_at: summary.pulled_at || null},
      me: {team_key: meKey, name: me.name, wins: s0.wins, losses: s0.losses, ties: s0.ties, rank: s0.rank, points_for: s0.pf},
      standings: standings, spread: spread, wins: winsOut, sim: simOut, need: need, goals: goals, games: gamesOut,
      sources: sources, missing: missing
    };
  }

  // ---------- moves aimed at one game ----------
  function movesFor(summary, weekly, me, w, slots, mine, cur, m) {
    var out = [];
    var roster = me.roster || [];
    // start/sit: only the current week has a live lineup to compare with
    if (w === cur && (!m || m.status !== "final")) {
      var startersNow = roster.filter(function (e) { return e.slot && e.slot !== "BN" && e.slot !== "IR"; }).map(function (e) { return playerWeek(weekly, e, w); });
      var nowTotal = startersNow.reduce(function (a, p) { return a + (p.points || 0); }, 0);
      var bestIds = mine.starters.map(function (s) { return s.player_id; });
      var ins = mine.starters.filter(function (s) { return s.player_id && startersNow.every(function (p) { return p.player_id !== s.player_id; }); });
      var outs = startersNow.filter(function (p) { return bestIds.indexOf(p.player_id) < 0; });
      if (ins.length && mine.total !== null && mine.total - nowTotal >= 0.5) {
        out.push({kind: "start", text: "Start " + ins.map(function (s) { return s.name; }).join(", ") + (outs.length ? " over " + outs.map(function (p) { return p.name; }).join(", ") : ""), gain: r1(mine.total - nowTotal), when: "before kickoff"});
      }
    }
    // watch: a starter listed Q or D
    if (w === cur) mine.starters.forEach(function (s) { // an injury designation is this week's news only
      if (!s.player_id || !/^(Q|D|GTD)$/i.test(String(s.status || ""))) return;
      var without = lineup(slots, roster.filter(function (e) { return e.player_id !== s.player_id; }).map(function (e) { return playerWeek(weekly, e, w); }));
      var sub = without.starters.filter(function (x) { return x.player_id && mine.starters.every(function (y) { return y.player_id !== x.player_id; }); })[0];
      out.push({kind: "watch", text: s.name + " is " + s.status + ": if he sits, " + (sub ? sub.name + " starts" : "the slot is empty"), gain: without.total !== null && mine.total !== null ? r1(without.total - mine.total) : null, when: w === cur ? "this week's lock" : null});
    });
    // adds from the free agents in the snapshot: the best lineup gain this week, dropping my least useful bench player
    var fas = summary.free_agents || [];
    if (fas.length && mine.total !== null) {
      var base = roster.map(function (e) { return playerWeek(weekly, e, w); });
      var cands = fas.map(function (fa) {
        var p = playerWeek(weekly, fa, w);
        if (p.points === null) return null;
        var l = lineup(slots, base.concat([p]));
        return l.total === null ? null : {fa: fa, p: p, gain: l.total - mine.total};
      }).filter(function (x) { return x && x.gain >= 2; }).sort(function (a, b) { return b.gain - a.gain; });
      var shown = {};
      cands.forEach(function (c) {
        if (shown[c.p.pos] || out.filter(function (o) { return o.kind === "add"; }).length >= 2) return;
        shown[c.p.pos] = true;
        var drop = dropCandidate(summary, weekly, roster.concat([c.fa]), slots, w, c.fa.player_id);
        out.push({kind: "add", text: "Add " + c.fa.name + " (" + c.p.pos + ", " + c.p.points.toFixed(1) + ")" + (drop ? "; drop " + drop.name : ""), gain: r1(c.gain), when: "before week " + w + " locks", player_id: c.fa.player_id, drop_id: drop ? drop.player_id : null});
      });
    }
    if (mine.empty_slots.length) out.push({kind: "bye", text: "No one to start at " + mine.empty_slots.join(", ") + " (byes or outs)", gain: null, when: null});
    return out;
  }
  // the bench player whose loss costs the least over the weeks left (weekly projections, never DDF Value)
  function dropCandidate(summary, weekly, roster, slots, fromWeek, keepId) {
    var weeks = (weekly.weeks || []).filter(function (w) { return w >= fromWeek; });
    var base = {}; weeks.forEach(function (w) { base[w] = teamWeek(summary, weekly, roster, w, slots).total; });
    var best = null;
    roster.forEach(function (e) {
      if (e.slot === "IR" || e.player_id === keepId) return;
      var rest = roster.filter(function (x) { return x.player_id !== e.player_id; });
      var cost = 0, ok = true, own = 0;
      weeks.forEach(function (w) {
        var t = teamWeek(summary, weekly, rest, w, slots).total; if (t === null || base[w] === null) ok = false; else cost += base[w] - t;
        own += playerWeek(weekly, e, w).points || 0;
      });
      // ties (several players the lineup never needs) go to the one with the fewest projected points
      if (ok && (best === null || cost < best.cost - 1e-9 || (Math.abs(cost - best.cost) < 1e-9 && own < best.own))) best = {player_id: e.player_id, name: e.name, cost: cost, own: own};
    });
    return best;
  }

  // ---------- Cover (Team page): what each starter's absence costs, week by week, and who covers ----------
  function teamOf(summary, key) { return (summary.teams || []).filter(function (t) { return t.team_key === key; })[0] || null; }
  function weeksLeft(summary, weekly) { var cur = num(summary.current_week) || 1; return (weekly.weeks || []).filter(function (w) { return w >= cur; }); }
  function cover(summary, weekly, teamKey) {
    var t = teamOf(summary, teamKey || summary.my_team_key); if (!t) throw new Error("Pick your team first.");
    var slots = slotsOf(summary), weeks = weeksLeft(summary, weekly), roster = t.roster || [];
    var base = {}; weeks.forEach(function (w) { base[w] = teamWeek(summary, weekly, roster, w, slots); });
    var startIds = {}; weeks.forEach(function (w) { base[w].starters.forEach(function (s) { if (s.player_id) startIds[s.player_id] = true; }); });
    var starters = roster.filter(function (e) { return startIds[e.player_id] && posOf(e) !== "K" && posOf(e) !== "DEF"; }).map(function (e) {
      var row = {player_id: e.player_id, name: e.name, pos: posOf(e), slot: e.slot || null, status: e.status || null, weeks: {}, total_cost: 0, worst: null, kind: "ok", shared_with: [], _covers: {}};
      var rest = roster.filter(function (x) { return x.player_id !== e.player_id; });
      weeks.forEach(function (w) {
        var me = playerWeek(weekly, e, w), b = base[w];
        var starts = b.starters.some(function (s) { return s.player_id === e.player_id; });
        if (!starts) { row.weeks[w] = {points: me.points, starts: false, bye: me.bye, cost: 0, cover: null}; return; }
        var without = lineup(slots, rest.map(function (x) { return playerWeek(weekly, x, w); }));
        var cost = b.total !== null && without.total !== null ? r1(b.total - without.total) : null;
        var inId = without.starters.filter(function (s) { return s.player_id && b.starters.every(function (y) { return y.player_id !== s.player_id; }); })[0] || null;
        var emptyNow = without.empty_slots.length > b.empty_slots.length;
        row.weeks[w] = {points: me.points, starts: true, bye: me.bye, cost: cost, cover: inId ? {player_id: inId.player_id, name: inId.name, points: inId.points} : null, empty: emptyNow};
        if (cost === null) row.total_cost = null; else if (row.total_cost !== null) row.total_cost = r1(row.total_cost + cost);
        if (cost !== null && (!row.worst || cost > row.worst.cost)) row.worst = {week: w, cost: cost};
        if (inId) row._covers[inId.player_id] = (row._covers[inId.player_id] || []).concat([w]);
        var share = me.points ? cost / me.points : null;
        if (emptyNow || (share !== null && share >= 0.5)) row.kind = "hole";
        else if (row.kind !== "hole" && share !== null && share >= 0.25) row.kind = "thin";
      });
      return row;
    });
    // shared cover: one backup covers two or more starters
    var by = {}; starters.forEach(function (r) { Object.keys(r._covers).forEach(function (c) { (by[c] = by[c] || []).push(r.player_id); }); });
    starters.forEach(function (r) {
      Object.keys(r._covers).forEach(function (c) { by[c].forEach(function (id) { if (id !== r.player_id && r.shared_with.indexOf(id) < 0) r.shared_with.push(id); }); });
      delete r._covers;
    });
    var rank = {hole: 0, thin: 1, ok: 2};
    starters.sort(function (a, b) { return rank[a.kind] - rank[b.kind] || (b.total_cost || 0) - (a.total_cost || 0); });
    // K and DEF: the starter, a backup on the roster, and the best add from the free agents in the data
    var fas = summary.free_agents || [];
    var kdef = ["K", "DEF"].filter(function (pos) { return slots.some(function (s) { return (ELIGIBLE[s] || []).indexOf(pos) >= 0; }); }).map(function (pos) {
      var mine = roster.filter(function (e) { return posOf(e) === pos && e.slot !== "IR"; });
      var tot = function (e) { return weeks.reduce(function (a, w) { return a + (playerWeek(weekly, e, w).points || 0); }, 0); };
      mine.sort(function (a, b) { return tot(b) - tot(a); });
      var cands = fas.filter(function (f) { return posOf(f) === pos; }).sort(function (a, b) { return tot(b) - tot(a); });
      var best = cands[0] || null, cost = {};
      weeks.forEach(function (w) {
        var s = mine[0] ? playerWeek(weekly, mine[0], w) : null, bk = mine[1] ? playerWeek(weekly, mine[1], w) : null;
        cost[w] = !s || s.points === null ? null : r1(s.points - (bk && bk.points !== null && !bk.bye ? bk.points : 0));
      });
      return {pos: pos, starter: mine[0] ? {player_id: mine[0].player_id, name: mine[0].name} : null, backup: mine[1] ? {player_id: mine[1].player_id, name: mine[1].name} : null,
        best_add: best ? {player_id: best.player_id, name: best.name, weeks: weeks.reduce(function (o, w) { o[w] = playerWeek(weekly, best, w).points; return o; }, {})} : null, cost: cost,
        starter_weeks: mine[0] ? weeks.reduce(function (o, w) { var x = playerWeek(weekly, mine[0], w); o[w] = {points: x.points, bye: x.bye}; return o; }, {}) : null};
    });
    var notes = ["Cost = your best lineup that week minus your best lineup without him, from weekly projections."];
    return {weeks: weeks, starters: starters, kdef: kdef, notes: notes};
  }

  // ---------- Build a Trade: both sides by week, and player by player ----------
  function swap(roster, outIds, ins) { return roster.filter(function (e) { return outIds.indexOf(e.player_id) < 0; }).concat(ins); }
  function tradeImpact(summary, weekly, myKey, partnerKey, giveIds, getIds, opts) {
    opts = opts || {};
    var me = teamOf(summary, myKey || summary.my_team_key), them = teamOf(summary, partnerKey);
    if (!me || !them) throw new Error("Pick both teams.");
    var slots = slotsOf(summary), weeks = weeksLeft(summary, weekly);
    var give = me.roster.filter(function (e) { return giveIds.indexOf(e.player_id) >= 0; });
    var get = them.roster.filter(function (e) { return getIds.indexOf(e.player_id) >= 0; });
    var myAfter = swap(me.roster, giveIds, get), theirAfter = swap(them.roster, getIds, give);
    var sd = opts.sd || fitSpread(summary).sd;
    var side = function (t, after) {
      var o = {team_key: t.team_key, name: t.name, before: {}, after: {}, delta: {}, total_delta: 0, lineups: {}};
      weeks.forEach(function (w) {
        var b = teamWeek(summary, weekly, t.roster, w, slots), a = teamWeek(summary, weekly, after, w, slots);
        o.before[w] = b.total; o.after[w] = a.total;
        o.delta[w] = b.total !== null && a.total !== null ? r1(a.total - b.total) : null;
        o.lineups[w] = {before: b, after: a};
        if (o.delta[w] === null) o.total_delta = null; else if (o.total_delta !== null) o.total_delta = r1(o.total_delta + o.delta[w]);
      });
      return o;
    };
    var sides = [side(me, myAfter), side(them, theirAfter)];
    var sched = {}; (summary.schedule || []).forEach(function (w) { sched[w.week] = w.matchups || []; });
    var games = weeks.map(function (w) {
      var m = (sched[w] || []).filter(function (x) { return x.team_keys && x.team_keys.indexOf(me.team_key) >= 0; })[0];
      if (!m) return {week: w, opp_name: null, is_partner: false, win_before: null, win_after: null};
      var ok = m.team_keys[1 - m.team_keys.indexOf(me.team_key)], opp = teamOf(summary, ok);
      var isP = ok === them.team_key;
      var ob = teamWeek(summary, weekly, opp.roster, w, slots).total;
      var oa = isP ? sides[1].after[w] : ob;
      var mb = sides[0].before[w], ma = sides[0].after[w];
      return {week: w, opp_name: opp.name, is_partner: isP,
        win_before: mb !== null && ob !== null ? r3(winChance(mb - ob, sd)) : null,
        win_after: ma !== null && oa !== null ? r3(winChance(ma - oa, sd)) : null};
    });
    var moving = give.map(function (e) { return {e: e, from: me, to: them}; }).concat(get.map(function (e) { return {e: e, from: them, to: me}; }));
    var players = moving.map(function (x) {
      var fromSide = x.from === me ? sides[0] : sides[1], toSide = x.to === me ? sides[0] : sides[1];
      var wk = {};
      weeks.forEach(function (w) {
        var p = playerWeek(weekly, x.e, w);
        var sb = fromSide.lineups[w].before.starters.some(function (s) { return s.player_id === x.e.player_id; });
        var sa = toSide.lineups[w].after.starters.some(function (s) { return s.player_id === x.e.player_id; });
        wk[w] = {points: p.points, source: p.source, bye: p.bye, note: p.note, starts_before: sb, starts_after: sa};
      });
      return {player_id: x.e.player_id, name: x.e.name, pos: posOf(x.e), nfl_team: x.e.nfl_team || null, status: x.e.status || null, from_team: x.from.name, to_team: x.to.name, weeks: wk};
    });
    sides.forEach(function (s) { delete s.lineups; });
    return {weeks: weeks, sides: sides, games: games, players: players};
  }

  // ---------- Trade & Waiver Recommendations: ranked by weekly gain ----------
  function recommendations(summary, weekly, myKey, opts) {
    opts = opts || {};
    var me = teamOf(summary, myKey || summary.my_team_key); if (!me) throw new Error("Pick your team first.");
    var slots = slotsOf(summary), weeks = weeksLeft(summary, weekly);
    var p = opts.plan || null;
    var weight = {}; // "For your games left": a week counts by its stake; unknown stakes count 1
    weeks.forEach(function (w) {
      var g = p ? p.games.filter(function (x) { return x.week === w; })[0] : null;
      var st = g ? (g.phase === "playoffs" ? 1 : Math.max(Math.abs(g.stake.playoffs || 0), Math.abs(g.stake.seed || 0) * 0.5)) : 1;
      weight[w] = g && g.phase === "playoffs" ? 1 : Math.max(0.05, st * 4); // a swing of 25 points of odds weighs like a playoff game
    });
    var base = {}; weeks.forEach(function (w) { base[w] = teamWeek(summary, weekly, me.roster, w, slots).total; });
    var gainOver = function (roster) {
      var by = {}, tot = 0, wt = 0, ok = true;
      weeks.forEach(function (w) {
        var t = teamWeek(summary, weekly, roster, w, slots).total;
        if (t === null || base[w] === null) { by[w] = null; ok = false; return; }
        by[w] = r1(t - base[w]); tot += t - base[w]; wt += (t - base[w]) * weight[w];
      });
      return {by: by, total: ok ? r1(tot) : null, weighted: ok ? r1(wt) : null};
    };
    // adds: each free agent, with the drop that costs least once he is in
    var adds = (summary.free_agents || []).map(function (fa) {
      var withFa = me.roster.concat([fa]);
      var drop = dropCandidate(summary, weekly, withFa, slots, weeks[0], fa.player_id);
      var after = drop ? withFa.filter(function (e) { return e.player_id !== drop.player_id; }) : withFa;
      var g = gainOver(after);
      return {player_id: fa.player_id, name: fa.name, pos: posOf(fa), nfl_team: fa.nfl_team || null, status: fa.status || null, percent_owned: num(fa.percent_owned),
        drop: drop ? {player_id: drop.player_id, name: drop.name} : null, gain_by_week: g.by, total_gain: g.total, weighted_gain: g.weighted};
    }).filter(function (a) { return a.total_gain !== null && a.total_gain >= 0.5; })
      .sort(function (a, b) { return b.total_gain - a.total_gain; }).slice(0, opts.maxAdds || 12);
    // trades: one for one with each other team, both sides' weekly lineups; kept when I gain and they do not lose much
    var trades = [];
    (summary.teams || []).forEach(function (t) {
      if (t.team_key === me.team_key) return;
      var tb = {}; weeks.forEach(function (w) { tb[w] = teamWeek(summary, weekly, t.roster, w, slots).total; });
      me.roster.forEach(function (gv) {
        if (gv.slot === "IR" || posOf(gv) === "K" || posOf(gv) === "DEF") return;
        t.roster.forEach(function (gt) {
          if (gt.slot === "IR" || posOf(gt) === "K" || posOf(gt) === "DEF") return;
          var mine = gainOver(swap(me.roster, [gv.player_id], [gt]));
          if (mine.total === null || mine.total < 2) return;
          var theirs = 0, tok = true, after = swap(t.roster, [gt.player_id], [gv]);
          weeks.forEach(function (w) { var a = teamWeek(summary, weekly, after, w, slots).total; if (a === null || tb[w] === null) tok = false; else theirs += a - tb[w]; });
          if (!tok || theirs < -(opts.partnerSlack || 1)) return;
          trades.push({partner_key: t.team_key, partner_name: t.name, give: [{player_id: gv.player_id, name: gv.name, pos: posOf(gv)}], get: [{player_id: gt.player_id, name: gt.name, pos: posOf(gt)}],
            my_gain_by_week: mine.by, my_total: mine.total, my_weighted: mine.weighted, their_total: r1(theirs), partner_plays_me_week: playsMe(summary, me.team_key, t.team_key, weeks)});
        });
      });
    });
    var key = opts.sort === "games" ? "my_weighted" : "my_total";
    trades.sort(function (a, b) { return (b[key] || 0) - (a[key] || 0); });
    if (opts.sort === "games") adds.sort(function (a, b) { return (b.weighted_gain || 0) - (a.weighted_gain || 0); });
    trades = trades.slice(0, opts.maxTrades || 15);
    // Your moves, in time order: the planner's per-game moves, by when they must happen
    var moves = [];
    if (p) p.games.forEach(function (g) {
      g.moves.forEach(function (m) {
        if (m.kind === "bye") return;
        moves.push({week: g.week, kind: m.kind, text: m.text, gain: m.gain, when: m.when || "week " + g.week, when_sort: g.week * 10 + (m.kind === "add" ? 0 : m.kind === "start" ? 2 : 1)});
      });
    });
    var dl = summary.settings && summary.settings.trade_deadline;
    if (trades.length && dl && dl.date) moves.push({week: null, kind: "trade", text: "Trade window: best idea " + trades[0].give[0].name + " for " + trades[0].get[0].name + " (" + (trades[0].my_total > 0 ? "+" : "") + trades[0].my_total + " over the weeks left)", gain: trades[0].my_total, when: "by " + dl.date + " (trade deadline)", when_sort: 0});
    moves.sort(function (a, b) { return a.when_sort - b.when_sort; });
    return {weeks: weeks, weight: weight, adds: adds, trades: trades, moves_in_time: moves};
  }
  function playsMe(summary, myKey, otherKey, weeks) {
    var hit = (summary.schedule || []).filter(function (w) { return weeks.indexOf(w.week) >= 0 && (w.matchups || []).some(function (m) { return m.team_keys && m.team_keys.indexOf(myKey) >= 0 && m.team_keys.indexOf(otherKey) >= 0; }); })[0];
    return hit ? hit.week : null;
  }

  root.DDFWeekly = {plan: plan, slotsOf: slotsOf, lineup: lineup, teamWeek: teamWeek, playerWeek: playerWeek, winChance: winChance, fitSpread: fitSpread, phi: phi, dropCandidate: dropCandidate, cover: cover, tradeImpact: tradeImpact, recommendations: recommendations};
})(typeof globalThis !== "undefined" ? globalThis : this);
