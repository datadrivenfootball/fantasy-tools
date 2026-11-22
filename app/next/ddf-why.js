/* "Why" for one trade (JEG-1561). Shared by find.html (offer cards) and any page that shows a trade.
 *
 * No value math of its own. Every number is TradeValueFinder output on the rows given: lineupValue / pickStarters
 * (starters by slot, before and after, so FLEX / SUPERFLEX re-slotting is visible), tradeFit (the same call
 * find-engine.js makes: starter change, bench change weighted by benchWeight, net, the Natural fit predicate) and
 * withChartAverage when a side is valued on the Analyst charts. This file only compares those outputs and words them.
 * Percent framing comes only from window.DDFOpportunity.rosterImprovementPct (JEG-1558); without it the % slot hides.
 *
 * Natural fit 2 (Jeremy, 2026-11-19): the panel's label is tradeFit's own (finder.js naturalFit, plus find-engine's waiver
 * demotion), never a second test. explain() also returns verdict {cls, word, charts, tags, misses}, lineups {you, them}
 * (slot rows before / after with tradeFit's starterBefore / starterAfter) and why {you:[..], them:[..]}: "Why you should
 * do this" and "Why they may see it as good". ctx.labels {you, them} names the valuations ("DDF", "the analyst charts");
 * trade.edge (find-engine's trade value) is named beside the bench-weighted value when they differ.
 *
 * API: window.DDFWhy
 *   explain(trade, ctx) -> {headline, pct:{sender, partner}|null, natural, needs:{you, them, youSurplus, themSurplus}, table:{give, get, net}, reasons:[{kind, text, amount}],
 *                           you:view, them:view, fit} or null when the inputs are missing or the trade is not judged
 *                           (no depth context, or an Analyst charts valuation without the charts: find-engine's `judged`)
 *     trade: {mine:[row], theirs:[row], give:[row], receive:[row], waiver?}  (whole rosters; give leaves mine, receive leaves
 *            theirs; waiver = find-engine's DDF.find.waiverAlternative result, JEG-1572: a demoted offer is never Natural)
 *   waiverLine(waiver, give) -> the plain-words waiver alternative ("The best available QB, X, closes N% of ...")
 *     ctx:   DDF.find.context() ({shape, expected, weights, analyst, ...}); optional ourKey (default ddf_value) and
 *            marketKey (default chart_avg when the analyst charts are available, else ourKey)
 *     view:  {key, starterDelta, benchDelta, net, posDelta:{QB,RB,WR,TE}, slots:{QB:{before, after, delta, from:[pos], to:[pos]}..},
 *             arriving:[{row, slot|null}], leaving:[{row, slot|null}], promoted:[{row, slot}], displaced:[row],
 *             emptyBefore, emptyAfter, unvalued:[row]}
 *   text(trade, ctx)    -> plain text of the same explanation (no "DDF", no team names)
 *   html(trade, ctx, opts) -> '<details class="why">..' tap-to-expand panel; opts.id (unique), opts.extra (html after the table),
 *                           opts.lineups false leaves out the two lineup tables (Build a Trade shows them in its own card)
 *   lineupTable(teamFitSide, shape, arrivingKeys, {natural, who}) -> one side's lineup in DDFLineup's shape (ddf-lineup.js)
 *   body(trade, ctx, opts) -> the panel's inside only (a page that renders <details> itself and fills it on first open)
 */
(function () {
  "use strict";
  var F = function () { return window.TradeValueFinder; };
  var POS = ["QB", "RB", "WR", "TE"];
  var SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  var FLOOR = 0.05;   // the display floor every page uses (a change under 0.05 shows as 0.0)
  var finite = function (v) { return typeof v === "number" && isFinite(v); };
  var keyOf = function (r) { return String(r.player_key); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var list = function (a) { return a.length < 2 ? a.join("") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]; };
  var article = function (pos) { return /^[AEFHILMNORSX]/.test(pos) ? "an " + pos : "a " + pos; };
  var shown = function (n) { return !finite(n) ? "—" : Math.abs(n) < FLOOR ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1); };

  function slotOf(picked, row) {
    var k = keyOf(row);
    for (var i = 0; i < SLOTS.length; i += 1) {
      if ((picked.slots[SLOTS[i]] || []).some(function (r) { return keyOf(r) === k; })) return SLOTS[i];
    }
    return null;
  }
  // One team in one point of view: lineupValue before / after, compared slot by slot and by player position.
  function view(roster, leaving, arriving, shape, key, fitSide) {
    var f = F();
    var gone = new Set(leaving.map(keyOf)), arrivingKeys = new Set(arriving.map(keyOf));
    var after = roster.filter(function (r) { return !gone.has(keyOf(r)); }).concat(arriving);
    var b = f.lineupValue(roster, shape, key), a = f.lineupValue(after, shape, key);
    var val = function (r) { return r.values[key]; };
    var sum = function (rows) { return rows.reduce(function (t, r) { return t + val(r); }, 0); };
    var slots = {};
    SLOTS.forEach(function (s) {
      if (!(shape && shape[s])) return;
      var bs = b.slots[s] || [], as = a.slots[s] || [];
      slots[s] = {before: sum(bs), after: sum(as), delta: sum(as) - sum(bs),
        from: bs.map(function (r) { return r.pos; }), to: as.map(function (r) { return r.pos; })};
    });
    var posDelta = {};
    POS.forEach(function (p) {
      var at = function (l) { return sum(l.starters.filter(function (r) { return r.pos === p; })); };
      posDelta[p] = at(a) - at(b);
    });
    var bStart = new Set(b.starters.map(keyOf)), aStart = new Set(a.starters.map(keyOf));
    var empty = function (l) { return Object.keys(l.empty).reduce(function (t, s) { return t + l.empty[s]; }, 0); };
    return {key: key,
      starterDelta: fitSide ? fitSide.starterDelta : a.starterValue - b.starterValue,
      benchDelta: fitSide ? fitSide.benchDelta : null,   // bench weighted by benchWeight (tradeFit); null when not judged
      net: fitSide ? fitSide.net : null,
      posDelta: posDelta, slots: slots,
      arriving: arriving.map(function (r) { return {row: r, slot: slotOf(a, r), valued: finite(r.values && r.values[key])}; }),
      leaving: leaving.map(function (r) { return {row: r, slot: slotOf(b, r), valued: finite(r.values && r.values[key])}; }),
      promoted: a.starters.filter(function (r) { return !bStart.has(keyOf(r)) && !arrivingKeys.has(keyOf(r)); }).map(function (r) { return {row: r, slot: slotOf(a, r)}; }),
      displaced: b.starters.filter(function (r) { return !aStart.has(keyOf(r)) && !gone.has(keyOf(r)); }),
      emptyBefore: empty(b), emptyAfter: empty(a),
      unvalued: leaving.concat(arriving).filter(function (r) { return !(r.values && finite(r.values[key])); })};
  }

  function keys(ctx) {
    var our = ctx.ourKey || "ddf_value";
    var market = ctx.marketKey || (ctx.analyst ? F().MARKET_KEY : our);
    return {our: our, market: market, avg: our === F().MARKET_KEY || market === F().MARKET_KEY};
  }
  // Need and surplus come from tradeFit's own depth readout (teamFit depth / towardAt / awayAt against the league's
  // expected players per position), not from value: a need is a position a side receives at where its depth moves toward
  // the expected range (it was short); a surplus is a position it gives from without going away from the range or
  // ending short (it had one to spare). No value math here.
  function depthNeeds(side, received) {
    if (!side || !side.ready) return [];
    return POS.filter(function (p) { return received.indexOf(p) >= 0 && side.towardAt.indexOf(p) >= 0; });
  }
  function depthSurplus(side, given) {
    if (!side || !side.ready) return [];
    return POS.filter(function (p) { var d = side.depth[p]; return given.indexOf(p) >= 0 && d && side.awayAt.indexOf(p) < 0 && d.statusAfter !== "under"; });
  }
  var positionsOf = function (rows) { return POS.filter(function (p) { return rows.some(function (r) { return r.pos === p; }); }); };
  function flexMoves(v) {
    return ["FLEX", "SUPERFLEX"].filter(function (s) {
      var x = v.slots[s];
      return x && x.from.slice().sort().join() !== x.to.slice().sort().join() && x.from.length && x.to.length;
    }).map(function (s) { return {slot: s, from: v.slots[s].from, to: v.slots[s].to, delta: v.slots[s].delta}; });
  }
  function benchShift(v) {
    // bench players by position, before vs after: who leaves the bench or joins it (no values, just counts)
    var moved = {};
    v.leaving.forEach(function (x) { if (!x.slot) moved[x.row.pos] = (moved[x.row.pos] || 0) - 1; });
    v.arriving.forEach(function (x) { if (!x.slot) moved[x.row.pos] = (moved[x.row.pos] || 0) + 1; });
    v.promoted.forEach(function (x) { moved[x.row.pos] = (moved[x.row.pos] || 0) - 1; });
    v.displaced.forEach(function (r) { moved[r.pos] = (moved[r.pos] || 0) + 1; });
    return {thinner: POS.filter(function (p) { return moved[p] < 0; }), deeper: POS.filter(function (p) { return moved[p] > 0; })};
  }
  var role = function (x) { return x.slot ? "starts at " + x.slot : x.valued ? "bench" : "no value yet"; };
  var roleBefore = function (x) { return x.slot ? "a starter at " + x.slot : x.valued ? "bench" : "no value yet"; };

  function reasons(you, them, trade, needs) {
    var out = [];
    var gone = you.unvalued.concat(them.unvalued.filter(function (r) { return you.unvalued.indexOf(r) < 0; }));
    if (gone.length) out.push({kind: "unvalued", amount: Infinity,
      text: list(gone.map(function (r) { return r.name; })) + (gone.length === 1 ? " has" : " have") + " no value yet, so " + (gone.length === 1 ? "it is" : "they are") + " left out here, never counted as 0."});
    POS.forEach(function (p) {
      var x = you.arriving.filter(function (y) { return y.row.pos === p; }).sort(function (a, b) { return (b.slot ? 1 : 0) - (a.slot ? 1 : 0); })[0];
      if (!x) return;
      var need = needs.you.indexOf(p) >= 0, gain = you.posDelta[p] >= FLOOR;
      if (!need && !gain) return;
      var bumped = you.displaced.filter(function (r) { return r.pos === p; })[0];
      var how = !x.slot ? "" : you.emptyBefore > you.emptyAfter ? ", a slot you could not fill before" : bumped ? ", ahead of " + bumped.name : "";
      out.push({kind: need ? "need" : "upgrade", pos: p, amount: Math.max(you.posDelta[p], need ? FLOOR : 0),
        text: (need ? "Fills your " + p + " need: " + x.row.name + (x.slot ? " " + role(x) : " adds " + p + " depth")
          : "Upgrades your " + p + " starters: " + x.row.name + " " + role(x)) + how + "."});
    });
    needs.youSurplus.forEach(function (p) {
      var d = you.fit.depth[p];
      out.push({kind: "surplus", pos: p, amount: FLOOR * 0.6, text: "You have " + p + " to spare: " + d.before + " counted now, " + d.after + " after (" + d.range + " expected)."});
    });
    POS.forEach(function (p) {
      if (!(you.posDelta[p] <= -FLOOR)) return;
      var left = you.leaving.filter(function (x) { return x.row.pos === p && x.slot; }).map(function (x) { return x.row.name; });
      var up = you.promoted.filter(function (x) { return x.row.pos === p; })[0];
      out.push({kind: "loss", pos: p, amount: -you.posDelta[p],
        text: "Your " + p + " starters get weaker" + (left.length ? " without " + list(left) : "") + (up ? "; " + up.row.name + " moves up from the bench" : "") + "."});
    });
    flexMoves(you).forEach(function (m) {
      out.push({kind: "flex", amount: Math.abs(m.delta), text: "Your " + m.slot + " changes from " + list(m.from.map(article)) + " to " + list(m.to.map(article)) + "."});
    });
    if (finite(you.benchDelta) && Math.abs(you.benchDelta) >= FLOOR) {
      var sh = benchShift(you), at = you.benchDelta < 0 ? sh.thinner : sh.deeper;
      out.push({kind: "bench", amount: Math.abs(you.benchDelta),
        text: "Your bench gets " + (you.benchDelta < 0 ? "thinner" : "deeper") + (at.length ? " at " + list(at) : "") + "."});
    }
    var opened = trade.give.length - trade.receive.length;
    if (opened > 0) out.push({kind: "spots", amount: FLOOR / 2,
      text: "You send " + trade.give.length + " players for " + trade.receive.length + ", which opens " + (opened === 1 ? "a roster spot" : opened + " roster spots") + "."});
    needs.them.forEach(function (p) {
      var x = them.arriving.filter(function (y) { return y.row.pos === p; })[0];
      out.push({kind: "partner", pos: p, amount: Math.max(them.posDelta[p], FLOOR), text: "They fill their " + p + " need with " + x.row.name + "."});
    });
    if (finite(them.starterDelta) && them.starterDelta <= -FLOOR) {
      var lost = POS.filter(function (p) { return them.posDelta[p] <= -FLOOR; });
      out.push({kind: "partner-loss", amount: -them.starterDelta, text: "Their starters get weaker" + (lost.length ? " at " + list(lost) : "") + "."});
    }
    return out.sort(function (a, b) { return b.amount - a.amount; });
  }

  // Natural fit 2 (Jeremy, 2026-11-19): the headline, the label and both "why" paragraphs read one test, tradeFit's
  // natural (finder.js naturalFit / naturalMisses / naturalTags), plus find-engine's waiver demotion. No test of its own.
  function headline(fit, verdict) {
    var n = fit.natural || {us: {}, them: {}};
    var mine = !n.us.value && fit.us.net <= FLOOR ? "This does not make your team better"
      : n.us.startersOk === false ? "Your starting lineup gets weaker"
      : n.us.reason === "starters" ? "Your starters get better"
      : n.us.reason === "need" ? "You fill a position you are short at"
        : n.us.reason === "bench" ? "Bench depth for you (your starting lineup does not change)"
          : n.us.value ? "Your total rises, but nothing in your lineup or depth improves" : "This does not make your team better";
    var theirs = n.them.startersOk === false ? "their starting lineup gets weaker on their valuation"
      : n.them.value && n.them.reason === "starters" ? "their starters get better on their valuation"
      : n.them.value && n.them.reason === "need" ? "they fill a position they are short at"
      : n.them.value && n.them.reason === "bench" ? "they add bench depth on their valuation (their starting lineup does not change)"
        : n.them.value ? "their total rises, but nothing in their lineup or depth improves"
          : fit.them.net < -FLOOR ? "they lose value on their valuation" : "they gain nothing on their valuation";
    var ok = verdict.cls === "natural";
    var theirGood = n.them.value && n.them.reason && n.them.startersOk !== false;
    return mine + (ok || (theirGood && n.us.startersOk !== false) ? ", and " : ", but ") + theirs + ".";
  }
  function netWords(v) {
    var w = function (n, up, down) { return !finite(n) ? null : n >= FLOOR ? up : n <= -FLOOR ? down : null; };
    var parts = [w(v.starterDelta, "starters better", "starters weaker"), w(v.benchDelta, "bench deeper", "bench thinner")].filter(Boolean);
    return parts.length ? parts.join(", ").replace(/^./, function (c) { return c.toUpperCase(); }) : "About even";
  }
  // The roster percent from JEG-1558 (DDFOpportunity.rosterImprovementPct): the module's own signed `shown` number (truncated
  // toward zero, one decimal, never -0) and its `band`; the sender-facing `sentence` is shown verbatim. Our only wording is
  // the short band name in the header line ("Your roster +0.9%. Theirs -1.2%, slightly worse"). Hidden when the module is
  // absent or either side is unsized (pct null).
  var BAND_NAME = {better: "better", unchanged: "essentially unchanged", slightly_worse: "slightly worse", clearly_worse: "clearly worse"};
  var signed = function (n) { return (n > 0 ? "+" : n < 0 ? "-" : "") + Math.abs(n).toFixed(1) + "%"; };
  function pct(trade, ctx, k) {
    var O = window.DDFOpportunity;
    if (!O || typeof O.rosterImprovementPct !== "function") return null;
    try {
      var octx = Object.assign({}, ctx, {senderKey: k.our, partnerKey: k.market, chartKeys: ctx.analyst || undefined});
      var s = O.rosterImprovementPct(trade, "sender", octx), p = O.rosterImprovementPct(trade, "partner", octx);
      if (!s || !p || !finite(s.pct) || !finite(p.pct) || !finite(s.shown) || !finite(p.shown) || !BAND_NAME[p.band]) return null;
      var you = "Your roster " + signed(s.shown), them = "Theirs " + signed(p.shown);
      return {sender: s, partner: p, you: signed(s.shown), them: signed(p.shown), band: BAND_NAME[p.band], sentence: p.sentence || "",
        line: you + ". " + them + ", " + BAND_NAME[p.band], text: you + ". " + them + ", " + BAND_NAME[p.band] + "." + (p.sentence ? " " + p.sentence : "")};
    } catch (e) { console.error(e); return null; }
  }

  // JEG-1572: the waiver alternative find-engine.js computed (DDF.find.waiverAlternative): the best available players at
  // the positions this trade brings you, and how much of the trade's starter gain they already get with nothing given up.
  // Words only; the numbers are find-engine's (two tradeFit calls). Waivers are never a trade partner.
  function waiverLine(w, give) {
    if (!w || !w.players || !w.players.length) return "";
    var names = w.players.map(function (p) { return p.name; }), pos = positionsOf(w.players);
    var many = names.length > 1;
    var who = pos.length === 1 ? "The best available " + pos[0] + (many ? "s" : "") : "The best available players at " + list(pos);
    var gave = (give || []).map(function (r) { return r.name; });
    var share = finite(w.covered) ? Math.round(w.covered * 100) : null;
    var first = share === null ? who + ", " + list(names) + ", " + (many ? "are" : "is") + " a pickup at the same position, with nothing given up."
      : share === 0
      ? who + ", " + list(names) + ", " + (many ? "do" : "does") + " not close the gap this trade fills."
      : who + ", " + list(names) + ", " + (many ? "close " : "closes ") + share + "% of the gap this trade fills, without giving up " + (gave.length ? list(gave) : "anyone") + ".";
    var added = " With " + (many ? "them" : names[0]) + " added, ";
    var beyond = w.ok && finite(w.gainAfter) && w.gainAfter >= FLOOR ? added + "this trade still adds " + shown(w.gainAfter) + " to your starters."
      : !w.ok && finite(w.gainAfter) && w.gainAfter >= FLOOR ? added + "this trade adds " + shown(w.gainAfter) + " to your starters, which no longer outweighs what you give up."
      : added + "this trade no longer makes your team better.";
    return share === 0 && w.ok ? first : first + beyond;
  }

  // ---------- Natural fit 2: lineups before and after, and the two "why" paragraphs (Jeremy, 2026-11-19) ----------
  var one = function (n) { return finite(n) ? n.toFixed(1) : "—"; };
  // Lineup flags (Build a Trade card, Find card chip; Jeremy, 2026-11-22): tests the Why already uses, read off teamFit
  // (empty slots, depth against the expected range, shortFilled) and tradeFit's Natural tags (bench depth only, thin).
  // natural: tradeFit's natural (null for one side alone); who: "you" or "them".
  function lineupFlags(t, natural, who) {
    var poss = who === "them" ? "their" : "your", out = [];
    var emptyB = t.lineupBefore.empty || {}, emptyA = t.lineupAfter.empty || {};
    Object.keys(emptyA).forEach(function (s) {
      var n = emptyA[s] - (emptyB[s] || 0);
      if (n > 0) out.push({kind: "empty", ok: false, slot: s, text: (n === 1 ? "Empty " + s + " slot" : n + " empty " + s + " slots") + " after the trade"});
    });
    POS.forEach(function (p) {
      var d = t.depth && t.depth[p];
      if (d && d.statusAfter === "under" && d.distAfter > d.distBefore) out.push({kind: "depth", ok: false, pos: p, text: p + " depth " + d.after + " after (" + d.range + " is normal)"});
    });
    (t.shortFilled || []).forEach(function (p) {
      var d = t.depth[p];
      out.push({kind: "filled", ok: true, pos: p, text: "Fills " + poss + " " + p + " need (" + d.before + " to " + d.after + ")"});
    });
    if (natural && (who === "them" ? natural.benchDepthThem : natural.benchDepth)) out.push({kind: "bench", ok: false, text: "Bench depth only"});
    if (natural && who === "them" && natural.thin) {
      var share = F() && finite(F().THIN_SHARE) ? Math.round(F().THIN_SHARE * 100) : 1;
      out.push({kind: "thin", ok: false, text: "Thin gain: under " + share + "% of their starters"});
    }
    return out;
  }
  // The bench before and after (lineupValue's own bench and benchValue), and who joins or leaves it, in plain words.
  function lineupBench(t, arrivingKeys) {
    var key = t.key, B = t.lineupBefore, A = t.lineupAfter;
    var row = function (r) { return {name: r.name, pos: r.pos, value: r.values ? r.values[key] : null}; };
    var inB = new Set(B.bench.map(keyOf)), inA = new Set(A.bench.map(keyOf));
    var startsA = new Set(A.starters.map(keyOf)), startedB = new Set(B.starters.map(keyOf));
    var left = B.bench.filter(function (r) { return !inA.has(keyOf(r)); }).map(function (r) { return {name: r.name, how: startsA.has(keyOf(r)) ? "up" : "traded"}; });
    var joined = A.bench.filter(function (r) { return !inB.has(keyOf(r)); }).map(function (r) { return {name: r.name, how: arrivingKeys.has(keyOf(r)) ? "arrives" : startedB.has(keyOf(r)) ? "down" : "joins"}; });
    return {before: B.bench.map(row), after: A.bench.map(row), valueBefore: B.benchValue, valueAfter: A.benchValue, left: left, joined: joined};
  }
  // K and DEF (shape K / DST): never valued, so never starters in lineupValue; their rows list who is rostered there.
  function lineupExtra(t, shape) {
    var out = [];
    [["K", ["K"], shape && shape.K], ["DEF", ["DEF", "DST"], shape && (shape.DST || shape.DEF)]].forEach(function (x) {
      var n = Number(x[2]) || 0;
      var at = function (l) { return (l.unvalued || []).filter(function (r) { return x[1].indexOf(r.pos) >= 0; }); };
      var b = at(t.lineupBefore), a = at(t.lineupAfter);
      for (var i = 0; i < n; i += 1) {
        out.push({slot: x[0], unvalued: true, before: b[i] ? {name: b[i].name, pos: x[0]} : null, after: a[i] ? {name: a[i].name, pos: x[0]} : null,
          changed: (b[i] ? keyOf(b[i]) : "") !== (a[i] ? keyOf(a[i]) : "")});
      }
    });
    return out;
  }
  // One team's starting lineup slot by slot, before and after, from tradeFit's own lineupValue calls (teamFit lineupBefore /
  // lineupAfter, starterBefore / starterAfter). A player in the same slot both times stays on one row; the rest pair up.
  // Also (DDFLineup's shape, 2026-11-22): moves (startersIn / startersOut with slots), bench, K / DEF rows (extra) and
  // flags; opts {natural, who} feeds the flags.
  function lineupTable(t, shape, arrivingKeys, opts) {
    opts = opts || {};
    arrivingKeys = arrivingKeys || new Set();
    var key = t.key, rows = [];
    // The injury flag (injury-flag.js) rides on the cell for display; it never enters a lineup or a total.
    var I = typeof window !== "undefined" && window.DDFInjury ? window.DDFInjury : null, fr = I ? I.freshness() : null;
    var startedBefore = new Set(t.lineupBefore.starters.map(keyOf));
    var cell = function (r, side) {
      if (!r) return null;
      var tag = side === "after" ? (arrivingKeys.has(keyOf(r)) ? "arrives" : startedBefore.has(keyOf(r)) ? "moves" : "from bench") : null;
      return {name: r.name, pos: r.pos, value: r.values ? r.values[key] : null, tag: tag, inj: I ? I.flagOf(r, fr) : null};
    };
    SLOTS.forEach(function (s) {
      if (!(shape && shape[s])) return;
      var B = (t.lineupBefore.slots[s] || []).slice(), A = (t.lineupAfter.slots[s] || []).slice();
      var inA = new Set(A.map(keyOf)), inB = new Set(B.map(keyOf));
      var addA = A.filter(function (r) { return !inB.has(keyOf(r)); });
      var lines = B.map(function (r) { return inA.has(keyOf(r)) ? {before: r, after: r} : {before: r, after: addA.shift() || null}; });
      addA.forEach(function (r) { lines.push({before: null, after: r}); });
      for (var i = lines.length; i < shape[s]; i += 1) lines.push({before: null, after: null});
      lines.forEach(function (l) {
        var same = l.before && l.after && keyOf(l.before) === keyOf(l.after);
        rows.push({slot: s, changed: !same && Boolean(l.before || l.after), before: cell(l.before, "before"), after: same ? cell(l.after, "same") : cell(l.after, "after")});
      });
    });
    var brief = function (x) { return {name: x.name, slot: x.slot}; };
    return {key: key, rows: rows, before: t.starterBefore, after: t.starterAfter, delta: t.starterAfter - t.starterBefore,
      into: t.startersIn.map(function (x) { return x.name; }), outOf: t.startersOut.map(function (x) { return x.name; }),
      moves: {"in": t.startersIn.map(brief), out: t.startersOut.map(brief)},
      bench: lineupBench(t, arrivingKeys), extra: lineupExtra(t, shape), flags: lineupFlags(t, opts.natural || null, opts.who || "you")};
  }
  // The lineup in one sentence per changed slot: "A replaces B at RB (19.6 for 11.4)".
  function lineupLines(table, who) {
    var out = [];
    table.rows.forEach(function (r) {
      if (!r.changed) return;
      if (r.after && !r.before) out.push(r.after.name + " fills " + who.poss + " empty " + r.slot + " slot (" + one(r.after.value) + ").");
      else if (!r.after) out.push(r.before.name + " leaves " + who.poss + " " + r.slot + " slot and nobody fills it.");
      else {
        var verb = r.after.tag === "moves" ? " moves to " + r.slot + " in place of " : r.after.tag === "from bench" ? " moves up from the bench to " + r.slot + " in place of " : " replaces ";
        out.push(r.after.name + verb + r.before.name + (r.after.tag === "arrives" ? " at " + r.slot : "") + " (" + one(r.after.value) + " for " + one(r.before.value) + ").");
      }
    });
    return out;
  }
  var names = function (rows) { return list(rows.map(function (r) { return r.name; })); };
  function depthLine(t, pos, who) {
    var d = t.depth && t.depth[pos];
    return d ? pos + " (" + d.before + " " + (who === "you" ? "now" : "before") + ", " + d.after + " after; " + d.range + " is normal)" : pos;
  }
  // "Why you should do this": what the trade does for your roster, in the order of the Natural test's reason.
  function yourWhy(fit, table, trade, units, waiverText) {
    var n = fit.natural, us = fit.us, out = [];
    var lines = lineupLines(table, {poss: "your"});
    if (!lines.length) out.push("No change to your starting lineup." + (trade.receive.length ? " " + names(trade.receive) + (trade.receive.length === 1 ? " joins" : " join") + " your bench." : ""));
    else out = out.concat(lines);
    out.push("Your starters: " + one(table.before) + " to " + one(table.after) + " (" + shown(table.delta) + " " + units.you + ").");
    if (n.us.need.length) out.push("Fills a position you are short at: " + list(n.us.need.map(function (p) { return depthLine(us, p, "you"); })) + ".");
    else if (n.us.slot) out.push("Fills a starting slot you could not fill before.");
    if (n.us.startersOk === false) out.push("Your best lineup gets weaker: your starters fall " + Math.abs(table.delta).toFixed(1) + " " + units.you + ".");
    if (n.us.reason === "bench") out.push("Bench depth, not a starter upgrade: your bench gains " + shown(us.benchDelta) + " " + units.you + " once bench players are weighted, at least 1% of your starters.");
    var value = "Value: " + shown(us.net) + " " + units.you + " once bench players are weighted";
    out.push(value + (finite(trade.edge) && Math.abs(trade.edge - us.net) >= FLOOR ? " (trade value " + shown(trade.edge) + " adds up raw player values)." : "."));
    POS.forEach(function (p) {
      var d = us.depth && us.depth[p];
      if (d && d.statusAfter === "under" && d.distAfter > d.distBefore) out.push("Watch " + p + " depth: " + d.after + " after the trade (" + d.range + " is normal).");
    });
    if (n.us.projections === false) out.push("Caution: your projection-based value falls " + Math.abs(n.us.projNet).toFixed(1) + ".");
    // JEG-1572: an offer a free pickup mostly matches leads with that pickup.
    if (waiverText) { if (trade.demoted) out.unshift(waiverText); else out.push(waiverText); }
    return out;
  }
  // "Why they may see it as good": the same on their valuation, the need it fills, the public charts and the cautions.
  function theirWhy(fit, table, trade, units) {
    var n = fit.natural, them = fit.them, out = [];
    var lines = lineupLines(table, {poss: "their"});
    if (!lines.length) out.push("No change to their starting lineup.");
    else out = out.concat(lines);
    out.push("Their starters: " + one(table.before) + " to " + one(table.after) + " (" + shown(table.delta) + " " + units.them + ").");
    if (n.them.need.length) out.push("They are short at " + list(n.them.need.map(function (p) { return depthLine(them, p, "them"); })) + " and get " + names(trade.give.filter(function (r) { return n.them.need.indexOf(r.pos) >= 0; })) + ".");
    if (n.them.reason === "bench") out.push("Bench depth for them, not a starter upgrade: their bench gains " + shown(them.benchDelta) + " " + units.them + " once bench players are weighted, at least 1% of their starters.");
    if (n.them.startersOk === false) out.push("Their best lineup gets weaker: their starters fall " + Math.abs(table.delta).toFixed(1) + " " + units.them + ", so they are unlikely to see it as good.");
    out.push("Their total: " + shown(them.net) + " " + units.them + " once bench players are weighted.");
    out.push(n.charts.agree + " of " + n.charts.total + " public trade charts call it even or better for them.");
    if (n.thin) out.push("Thin for them: the gain is " + (Math.floor(n.them.share * 1000) / 10).toFixed(1) + "% of their starters, so they may see it as close.");
    var projPct = finite(n.them.projShare) ? " (" + (Math.floor(Math.abs(n.them.projShare) * 1000) / 10).toFixed(1) + "% of their starters on projections)" : "";
    if (n.them.projBlock) out.push("Our projections disagree strongly: their projection-based value falls " + Math.abs(n.them.projNet).toFixed(1) + projPct + ", more than 5%, so it is not a natural fit.");
    else if (n.them.caution) out.push("Caution: our projections disagree. Their projection-based value falls " + Math.abs(n.them.projNet).toFixed(1) + projPct + ".");
    return out;
  }
  var VERDICT = {natural: "Natural fit", neutral: "Partner neutral", force: "Force fit"};
  // The card's class, read the way find-engine.js classify reads it (DDF.find.classify when the page has it), plus the
  // waiver demotion: one label for the card and the panel.
  function verdictOf(fit, demoted, names) {
    var D = window.DDF && window.DDF.find;
    var cls = D && D.classify ? D.classify({fit: fit}) : fit.label === "natural" ? "natural" : fit.them.net >= -fit.them.tau ? "neutral" : "force";
    if (cls === "natural" && demoted) cls = "neutral";
    var f = F(), n = fit.natural;
    var misses = cls === "natural" ? [] : f.naturalMisses(fit, names).concat(demoted ? ["a free pickup gets most of this gain"] : []);
    return {cls: cls, word: VERDICT[cls] || cls, charts: n.charts.agree + "/" + n.charts.total, tags: cls === "natural" ? f.naturalTags(fit) : [], misses: misses};
  }

  function explain(trade, ctx) {
    var f = F();
    if (!f || !trade || !ctx || !ctx.shape || !Array.isArray(trade.mine) || !Array.isArray(trade.theirs)) return null;
    var k = keys(ctx);
    if (!ctx.expected || (k.avg && !ctx.analyst)) return null;   // find-engine's `judged`: no chart average, no depth -> not judged
    var widen = function (rows) { return k.avg && ctx.analyst ? f.withChartAverage(rows, ctx.analyst) : rows; };
    var mine = widen(trade.mine), theirs = widen(trade.theirs);
    var byKey = new Map(mine.concat(theirs).map(function (r) { return [keyOf(r), r]; }));
    var wide = function (rows) { return rows.map(function (r) { return byKey.get(keyOf(r)) || widen([r])[0]; }); };
    var give = wide(trade.give || []), recv = wide(trade.receive || []);
    // The fit exactly as find-engine.js computes it (both sides, Natural fit predicate, bench weighted by benchWeight).
    var fit = f.tradeFit({mine: {roster: mine, leaving: give, arriving: recv}, theirs: {roster: theirs, leaving: recv, arriving: give}},
      {shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, ourKey: k.our, marketKey: k.market, chartKeys: ctx.analyst || undefined, gateKeys: ctx.gate || undefined, z: f.FIT_Z});
    if (!fit) return null;   // the trade is not judged (find-engine leaves it unjudged): no Why
    var you = view(mine, give, recv, ctx.shape, k.our, fit.us);
    var them = view(theirs, recv, give, ctx.shape, k.market, fit.them);
    you.fit = fit.us; them.fit = fit.them;
    them.clearlyWorse = Boolean(fit.natural && fit.natural.them && fit.natural.them.pctOk === false);
    var gp = positionsOf(give), rp = positionsOf(recv);
    var needs = {you: depthNeeds(fit.us, rp), them: depthNeeds(fit.them, gp), youSurplus: depthSurplus(fit.us, gp), themSurplus: depthSurplus(fit.them, rp)};
    // JEG-1572: never "Natural fit" when a free pickup mostly matches the trade (find-engine moved the offer to neutral).
    var waiver = trade.waiver || null, demoted = Boolean(waiver && waiver.demoted);
    // The page's names for the two valuations (find.html: "DDF", "the analyst charts"); generic without them.
    var names = {you: (ctx.labels && ctx.labels.you) || "your valuation", them: (ctx.labels && ctx.labels.them) || "their valuation"};
    var verdict = verdictOf(fit, demoted, names);
    var natural = verdict.cls === "natural";
    var rs = reasons(you, them, {give: give, receive: recv}, needs);
    var wl = waiverLine(waiver, give);
    // A demoted offer leads with the waiver option; otherwise it follows the biggest reasons (amount: the gain it matches).
    if (wl) rs.push({kind: "waiver", amount: demoted ? Infinity : Math.max(0, (waiver.gain || 0) * (waiver.covered || 0)), text: wl});
    rs.sort(function (a, b) { return (b.kind === "unvalued") - (a.kind === "unvalued") || b.amount - a.amount; });
    var p = pct({mine: trade.mine, theirs: trade.theirs, give: trade.give, receive: trade.receive}, ctx, k);
    var unit = function (n) { return n === "DDF" ? "DDF" : "on " + n; };
    var units = {you: unit(names.you), them: unit(names.them)};
    var lineups = {you: lineupTable(fit.us, ctx.shape, new Set(recv.map(keyOf)), {natural: fit.natural, who: "you"}),
      them: lineupTable(fit.them, ctx.shape, new Set(give.map(keyOf)), {natural: fit.natural, who: "them"})};
    var edge = finite(trade.edge) ? trade.edge : null;
    var why = {you: yourWhy(fit, lineups.you, {give: give, receive: recv, edge: edge, demoted: demoted}, units, wl),
      them: theirWhy(fit, lineups.them, {give: give, receive: recv}, units)};
    return {headline: headline(fit, verdict), verdict: verdict, lineups: lineups, why: why, pct: p, natural: natural, needs: needs, waiver: waiver ? {line: wl, demoted: demoted} : null,
      table: {give: you.leaving.map(function (x) { return {name: x.row.name, pos: x.row.pos, role: roleBefore(x)}; }),
        get: you.arriving.map(function (x) { return {name: x.row.name, pos: x.row.pos, role: role(x)}; }),
        net: netWords(you)},
      reasons: rs.slice(0, 3), allReasons: rs, you: you, them: them, fit: fit};
  }

  function verdictLine(e) {
    var v = e.verdict;
    if (v.cls === "natural") return v.word + " (" + v.charts + " public charts)" + (v.tags.length ? ": " + v.tags.join(", ") : "") + ".";
    return v.word + ". Not a natural fit: " + v.misses.join("; ") + ".";
  }
  function text(trade, ctx) {
    var e = explain(trade, ctx);
    if (!e) return "";
    var bullets = function (a) { return a.map(function (x) { return "- " + x; }); };
    return [e.headline, e.pct ? e.pct.text : null, "Why you should do this:"].concat(bullets(e.why.you), ["Why they may see it as good:"], bullets(e.why.them), [verdictLine(e)])
      .filter(Boolean).join("\n");
  }

  var CSS = ".why{margin-top:8px}.why>summary{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:0 14px;border:1px solid #176c4d;border-radius:99px;color:#176c4d;font-weight:700;font-size:14px;cursor:pointer;list-style:none;background:#fff}"
    + ".why>summary::-webkit-details-marker{display:none}.why>summary::after{content:\"\\25BE\";font-size:12px}.why[open]>summary::after{content:\"\\25B4\"}"
    + ".why>summary:focus-visible,.why .why-raw>summary:focus-visible{outline:3px solid #176c4d;outline-offset:2px}"
    + ".why .why-body{margin-top:8px;padding:12px 14px;border:1px solid #dbe0dc;border-radius:10px;background:#fbfcfb}"
    + ".why .why-head{margin:0 0 6px;font-weight:700;font-size:15px;line-height:1.4}.why .why-tag{display:inline-block;font-size:12px;font-weight:700;border-radius:99px;padding:2px 10px;background:#176c4d;color:#fff;margin-right:8px}"
    + ".why .why-pct{margin:0 0 8px;font-size:14px}.why table{width:100%;border-collapse:collapse;font-size:14px;margin:4px 0 8px}.why th{background:none;text-align:left;font-size:12px;color:#5c6a76;width:7.5em;vertical-align:top;padding:6px 8px 6px 0;border-bottom:1px solid #eef1ec;white-space:normal}"
    + ".why td{padding:6px 0;border-bottom:1px solid #eef1ec;overflow-wrap:anywhere}.why ol{margin:6px 0 4px;padding-left:20px;font-size:14px;line-height:1.45}"
    + ".why .why-raw>summary{display:inline-flex;align-items:center;min-height:44px;color:#176c4d;font-size:13px;font-weight:600;cursor:pointer}.why .why-raw table{font-family:'IBM Plex Mono',monospace;font-size:12.5px}"
    // A host page may restyle tables as phone cards (find.html): the panel's tables stay tables.
    + ".why table{display:table!important}.why tbody{display:table-row-group!important}.why tr{display:table-row!important;padding:0!important;border:0!important}"
    + ".why th,.why td{display:table-cell!important;text-align:left!important}.why td:before{content:none!important;display:none!important}"
    + ".why .why-raw td{white-space:nowrap;overflow-wrap:normal;padding-right:12px}.why .why-charts a{color:#176c4d;font-weight:700}"
    // Natural fit 2: the two lineups before and after (stacked on a phone, side by side from 700px), the two "why" lists.
    + ".why .why-tag[data-cls=neutral]{background:#fbefd9;color:#7a4800}.why .why-tag[data-cls=force]{background:#f8e4e0;color:#8f2c20}.why .why-tag2{background:#e3f1ea;color:#176c4d}"
    + ".why .why-lus{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;margin:8px 0 10px}@media(min-width:700px){.why .why-lus{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}"
    + ".why .why-lu{min-width:0}.why .why-lu-h{margin:0 0 4px;font-size:14px}.why .why-lu-h small{color:#5c6a76}"
    + ".why table.why-lt{table-layout:fixed;margin:0}.why .why-lt th{width:auto;padding:5px 4px 5px 0;font-size:11px;text-transform:uppercase;letter-spacing:.04em}"
    + ".why .why-lt thead th:first-child,.why .why-lt tbody th{width:3.4em}.why .why-lt td{padding:5px 6px 5px 0;vertical-align:top;font-size:13.5px}"
    + ".why .why-nm{display:block;line-height:1.25;overflow-wrap:anywhere}.why .why-v{font-family:'IBM Plex Mono',monospace;font-size:12px;color:#5c6a76}"
    + ".why .why-mv{display:inline-block;margin-left:6px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#176c4d}.why .why-mv[data-tag=moves],.why .why-mv[data-tag='from bench']{color:#7a4800}"
    + ".why tr.why-chg td:first-of-type .why-nm{color:#5c6a76;text-decoration:line-through}.why tr.why-chg td:last-child{background:#e3f1ea}.why tr.why-chg td:last-child .why-nm{font-weight:700}.why .why-empty{color:#8f2c20}"
    + ".why .why-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}"
    + ".why .why-tot{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;margin:4px 0 0;padding-top:6px;border-top:2px solid #18231d;font-size:14px}.why .why-tot>span:first-child{font-weight:700;margin-right:auto}"
    + ".why .why-n{font-family:'IBM Plex Mono',monospace}.why .why-d{font-family:'IBM Plex Mono',monospace;font-weight:700;padding:1px 8px;border-radius:6px;background:#e9ecef}.why .why-d[data-dir=up]{background:#e3f1ea;color:#176c4d}.why .why-d[data-dir=down]{background:#f8e4e0;color:#8f2c20}"
    + ".why .why-side{margin:10px 0 2px;font-weight:700;font-size:14px}.why ul{margin:2px 0 6px;padding-left:20px;font-size:14px;line-height:1.45}.why .why-verdict{margin:8px 0 4px;padding-top:8px;border-top:1px solid #eef1ec;font-size:14px;font-weight:600}";
  function injectCss() {
    if (document.getElementById("ddf-why-css")) return;
    var s = document.createElement("style");
    s.id = "ddf-why-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }
  function html(trade, ctx, opts) {
    opts = opts || {};
    var e = explain(trade, ctx);
    if (!e) return "";
    if (typeof document !== "undefined") injectCss();
    return '<details class="why"' + (opts.id ? ' id="' + esc(opts.id) + '"' : "") + ' data-why' + (e.natural ? " data-natural" : "") + '><summary>Why</summary>'
      + bodyOf(e, withInjury(trade, opts)) + "</details>";
  }
  // The panel's inside (for a page that renders the <details> itself and fills it on first open).
  function body(trade, ctx, opts) {
    var e = explain(trade, ctx);
    if (!e) return "";
    if (typeof document !== "undefined") injectCss();
    return bodyOf(e, withInjury(trade, opts));
  }
  // The injury flag's lines (injury-flag.js) for the players in the offer: display only, after the verdict head.
  function withInjury(trade, opts) {
    var I = typeof window !== "undefined" && window.DDFInjury ? window.DDFInjury : null;
    return Object.assign({}, opts || {}, {injury: I ? I.whyHtml((trade.give || []).concat(trade.receive || [])) : ""});
  }
  // The two lineup tables ("full" size of the shared DDFLineup, ddf-lineup.js). Build a Trade leaves them out (opts.lineups
  // false): its own lineup card shows them (Jeremy, 2026-11-22).
  function lineupHtml(t, title, sub) {
    return window.DDFLineup ? window.DDFLineup.html(t, {size: "full", title: title, basis: sub}) : "";
  }
  function bodyOf(e, opts) {
    var you = e.you, them = e.them, v = e.verdict, units = opts.units || {};
    var raw = '<details class="why-raw"><summary>Show the numbers</summary><table><tr><th></th><td>You</td><td>Them</td></tr>'
      + "<tr><th>Starters</th><td>" + shown(you.starterDelta) + "</td><td>" + shown(them.starterDelta) + "</td></tr>"
      + "<tr><th>Bench (weighted)</th><td>" + shown(you.benchDelta) + "</td><td>" + shown(them.benchDelta) + "</td></tr>"
      + "<tr><th>Net</th><td>" + shown(you.net) + "</td><td>" + shown(them.net) + "</td></tr>"
      + POS.map(function (p) { return "<tr><th>" + p + " starters</th><td>" + shown(you.posDelta[p]) + "</td><td>" + shown(them.posDelta[p]) + "</td></tr>"; }).join("")
      + "</table></details>";
    var ul = function (a, attr) { return "<ul " + attr + ">" + a.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>"; };
    return '<div class="why-body" data-natural="' + (e.natural ? "1" : "0") + '" data-cls="' + esc(v.cls) + '">'
      + '<p class="why-head"><span class="why-tag" data-cls="' + esc(v.cls) + '">' + esc(v.word) + (v.cls === "natural" ? " · " + esc(v.charts) + " public charts" : "") + "</span>"
      + v.tags.map(function (t) { return '<span class="why-tag why-tag2" data-tag>' + esc(t) + "</span>"; }).join("") + esc(e.headline) + "</p>"
      + (opts.injury || "")
      + (e.pct ? '<p class="why-pct" data-pct data-band="' + esc(e.pct.partner.band) + '">' + esc(e.pct.line) + "." + (e.pct.sentence ? " <span class=\"why-sentence\">" + esc(e.pct.sentence) + "</span>" : "") + "</p>" : "")
      + (opts.lineups === false ? "" : '<div class="why-lus">' + lineupHtml(e.lineups.you, "Your lineup", units.youSub || "your valuation") + lineupHtml(e.lineups.them, opts.partner ? opts.partner + " lineup" : "Their lineup", units.themSub || "their valuation") + "</div>")
      + '<p class="why-side">Why you should do this</p>' + ul(e.why.you, "data-why-you")
      + '<p class="why-side">Why they may see it as good</p>' + ul(e.why.them, "data-why-them")
      + '<p class="why-verdict" data-verdict="' + esc(v.cls) + '">' + esc(verdictLine(e)) + "</p>"
      + (opts.extra || "")
      + raw + "</div>";
  }

  if (typeof document !== "undefined" && document.head) injectCss();
  window.DDFWhy = {explain: explain, text: text, html: html, body: body, waiverLine: waiverLine, lineupTable: lineupTable, FLOOR: FLOOR};
})();
