/* DDF staging: Trade & Waiver Recommendations, weekly numbers on the live cards (JEG-1736, piece 3).
 * Jeremy, 2026-11-27: "The trade and waivers screens from the live site should upgrade to include these new features,
 * not create duplicate screens from new info; enrich not replace."
 * Loaded by league-bridge.js (data-add) after the live find page is in the document. This file lists no trades and no
 * pickups of its own. It does three things:
 *   1. "Your moves, in time order": the one panel the live site has no screen for. Its trade line is the live offer
 *      card with the highest expected $ (below), never a trade found here.
 *   2. Every live offer card ([data-offer]) and pickup card ([data-pickup]) gets a compact weekly block inside it:
 *      expected $ for your games left, points over the weeks left, one chip per week, and who the partner plays.
 *   3. One more option in the live Sort control, "Games left (expected $)", the default while the league is
 *      connected. It reorders the cards inside each live list; the live options keep working as they do.
 * The live page redraws its cards on every filter and sort change, so the block is re-applied (idempotent, by a
 * signature on the card) and each card's numbers are worked out once and kept.
 * Weekly projections only, never DDF Value. A missing value is never 0: it renders as "—" with its reason.
 * Every league string is written with textContent, never as HTML. */
(function () {
  "use strict";
  var QS = new URLSearchParams(location.search);
  var IS_LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  var MOCK = IS_LOCAL && QS.get("mock") === "1"; /* sample league, local preview only */
  var SELF = document.currentScript && document.currentScript.src;
  var W = window.DDFWeekly;
  var KINDS = {start: "Start", add: "Add", watch: "Watch", trade: "Trade", assumed: "Assumed"};
  var MOVES_SHOWN = 6;
  var SORT_VALUE = "fw-games"; /* our option in the live #sort; the live sorter treats an unknown value as its first option */
  var NO_PROJ = "A starter has no projection in one of the weeks left";
  var state = {data: null, plan: null, moves: [], usd: false, cache: {}, queue: [], queued: {}, running: false, best: null, bestSig: null, movesBox: null, showAllMoves: false};

  function el(tag, attrs) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] == null || attrs[k] === false) return;
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) { var c = arguments[i]; if (c != null && c !== false) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    return n;
  }
  var isNum = function (x) { return typeof x === "number" && isFinite(x); };
  function na(reason) { var r = reason || "Not available"; return el("span", {class: "fw-na", title: r, "aria-label": "Not available. " + r, text: "—"}); }
  function signed(x) { return (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(1); }
  function pts(x) { return signed(x) + " pts"; }
  function winDelta(before, after) { /* change in win chance, in whole points of percent */
    if (!isNum(before) || !isNum(after)) return null;
    var d = Math.round((after - before) * 100);
    return (d > 0 ? "+" : d < 0 ? "−" : "±") + Math.abs(d) + "% win";
  }
  function dates(s) { /* "by 2026-11-28 (trade deadline)" -> "by Nov 28 (trade deadline)" */
    return String(s || "").replace(/\b(\d{4})-(\d\d)-(\d\d)\b/g, function (m, y, mo, d) {
      var dt = new Date(Date.UTC(+y, +mo - 1, +d));
      return isNaN(dt) ? m : dt.toLocaleDateString(undefined, {month: "short", day: "numeric", timeZone: "UTC"});
    });
  }
  function gameOf(week) { return state.plan.games.filter(function (g) { return g.week === week; })[0] || null; }
  function gameLabel(week) {
    var g = gameOf(week);
    if (!g) return "Week " + week;
    if (g.opp && g.opp.name) return "Week " + week + " vs " + g.opp.name;
    return "Week " + week + (g.phase === "playoffs" ? " (playoffs)" : "");
  }

  /* ---------- per-week chips: points gained, and the change in win chance where the game is known ---------- */
  function chip(week, gain, winText, why) {
    if (isNum(gain) && Math.abs(gain) < 0.05) winText = null; /* nothing moves this week */
    var dir = !isNum(gain) ? "na" : gain >= 0.05 ? "up" : gain <= -0.05 ? "down" : "flat";
    var g = gameOf(week);
    var label = gameLabel(week) + ": " + (isNum(gain) ? pts(gain) : "not available") + (winText ? ", " + winText : "") + (why ? ". " + why : "");
    var c = el("li", {class: "fw-chip", "data-dir": dir, title: label, "aria-label": label},
      el("span", {class: "fw-wk", text: "W" + week}),
      isNum(gain) ? el("b", {text: dir === "flat" ? "0.0" : signed(gain)}) : na(why || "A starter has no projection this week"),
      winText ? el("span", {class: "fw-win", text: winText}) : null);
    if (g && g.phase === "playoffs") c.setAttribute("data-playoff", "");
    return c;
  }
  function chipsOf(weeks, delta, games) { /* one chip per week left: my points gained, and my win chance where the game is known */
    var ul = el("ul", {class: "fw-chips", "aria-label": "Your gain by week"});
    weeks.forEach(function (w) {
      var gm = (games || []).filter(function (x) { return x.week === w; })[0], g = gameOf(w);
      var win = gm ? winDelta(gm.win_before, gm.win_after) : null;
      ul.appendChild(chip(w, delta[w], win, !win && g && !g.opp ? (g.opp_note || "Opponent not set yet, so no win chance") : null));
    });
    return ul;
  }

  /* ---------- the league data behind a live card ---------- */
  function norm(s) { return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[.'’]/g, "").replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "").replace(/[^a-z0-9]+/g, " ").trim(); }
  function posOf(p) { var x = String(p || "").toUpperCase(); return x === "DST" || x === "D/ST" ? "DEF" : x; }
  function keysOf(s) { return String(s || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean); }
  function enginePlayer(key) { try { return window.DDF && DDF.engine && DDF.engine.player ? DDF.engine.player(key) : null; } catch (e) { return null; } }
  function nameOfKey(key) { var p = enginePlayer(key); return p && p.n ? p.n : "A player"; }
  function myKey() { return state.plan.me.team_key; }
  function matchedTeam(teamKey) { /* {engine key: stored player_id} for one team, from the bridge's roster match */
    var S = window.DDFStaging, out = {};
    ((S && S.matched && S.matched.teams) || []).forEach(function (tm) { if (tm.team_key === teamKey) (tm.players || []).forEach(function (p) { if (p.player_id) out[String(p.key)] = p.player_id; }); });
    return out;
  }
  function idsFor(keys, map, teamName) { /* stored ids for a card's engine keys, or the reason one is missing */
    var ids = [], miss = [];
    keys.forEach(function (k) { if (map[k]) ids.push(map[k]); else miss.push(nameOfKey(k)); });
    return miss.length ? {why: miss.join(", ") + (miss.length === 1 ? " is" : " are") + " not matched to a player on " + teamName + " in the league data"} : {ids: ids};
  }
  function dollarText(v) { return (v <= -0.005 ? "−$" : v >= 0.005 ? "+$" : "$") + Math.abs(v).toFixed(2); }
  function rosterName(teamKey, id) {
    var t = (state.data.summary.teams || []).filter(function (x) { return x.team_key === teamKey; })[0];
    var p = t ? (t.roster || []).filter(function (x) { return x.player_id === id; })[0] : null;
    return p ? p.name : "a player";
  }

  /* one live offer card -> {sig, run}: run() works the numbers out (DDFWeekly.tradeImpact), once per signature */
  function offerJob(card) {
    var give = keysOf(card.dataset.give), get = keysOf(card.dataset.receive), partner = card.dataset.partner || "";
    return {sig: "t|" + partner + "|" + give.join(",") + "|" + get.join(","), run: function () {
      var sm = state.data.summary, mine = matchedTeam(myKey());
      var teams = (sm.teams || []).filter(function (t) { return t.name === partner && t.team_key !== myKey(); });
      if (!teams.length) return {why: "The trading partner is not a team in the league data"};
      /* two teams can share a name: the partner is the one that holds every player you get */
      var pt = teams.filter(function (t) { var m = matchedTeam(t.team_key); return get.every(function (k) { return m[k]; }); })[0] || teams[0];
      var g = idsFor(give, mine, "your team"), r = idsFor(get, matchedTeam(pt.team_key), pt.name);
      if (g.why || r.why) return {why: g.why || r.why};
      if (!g.ids.length || !r.ids.length) return {why: "The card names no players on one side"};
      var imp = W.tradeImpact(sm, state.data.weekly, myKey(), pt.team_key, g.ids, r.ids, {sd: state.plan.spread && state.plan.spread.sd});
      var total = imp.sides[0].total_delta;
      return {kind: "offer", partner: pt.name, weeks: imp.weeks, delta: imp.sides[0].delta, their: imp.sides[1].delta, games: imp.games, total: total,
        /* priced only when every week has a number: a week left out would understate it */
        dollars: isNum(total) ? W.dollarsFor(state.plan, imp.sides[0].delta) : null,
        give: g.ids.map(function (id) { return rosterName(myKey(), id); }), get: r.ids.map(function (id) { return rosterName(pt.team_key, id); })};
    }};
  }
  /* one live pickup card -> {sig, run} (DDFWeekly.addImpact, with the drop the live card names) */
  function pickupJob(card) {
    var add = String(card.dataset.add || ""), drop = String(card.dataset.drop || "");
    return {sig: "a|" + add + "|" + drop, run: function () {
      var sm = state.data.summary, p = enginePlayer(add);
      if (!p || !p.n) return {why: "this player is not in the page's player data"};
      var fa = (sm.free_agents || []).filter(function (f) { return norm(f.name) === norm(p.n) && posOf(f.position) === posOf(p.pos); })[0];
      if (!fa) return {why: "not in the league's free-agent list from the league data"};
      var dropId = null;
      if (drop) { dropId = matchedTeam(myKey())[drop] || null; if (!dropId) return {why: nameOfKey(drop) + ", the drop, is not matched to a player on your team in the league data"}; }
      var a = W.addImpact(sm, state.data.weekly, myKey(), fa, dropId, {plan: state.plan, sd: state.plan.spread && state.plan.spread.sd});
      if (!a) return {why: "the league data has no team for you"};
      return {kind: "pickup", weeks: a.weeks, delta: a.delta, games: a.games, total: a.total, dollars: isNum(a.total) ? a.dollars : null, rivals: a.rivals || [],
        /* the live card names no drop: with an open roster spot nobody goes; with a full roster addImpact counts the
           cheapest drop and the card says who */
        assumedDrop: !drop && a.drop ? a.drop.name : null};
    }};
  }

  /* ---------- the block inside a live card ---------- */
  function headLine(res) {
    var p = el("p", {class: "fw-line"});
    if (state.usd) {
      p.appendChild(el("span", {class: "fw-lab", text: "Expected $, your games left "}));
      p.appendChild(isNum(res.dollars) ? el("b", {"data-dir": res.dollars >= 0.005 ? "up" : res.dollars <= -0.005 ? "down" : "flat", text: dollarText(res.dollars)}) : na(NO_PROJ));
      p.appendChild(document.createTextNode(" · "));
    } else p.appendChild(el("span", {class: "fw-lab", text: "Weekly points, your games left "}));
    if (isNum(res.total)) p.appendChild(el(state.usd ? "span" : "b", {text: pts(res.total)}));
    else p.appendChild(na(NO_PROJ));
    p.appendChild(document.createTextNode(" over the weeks left"));
    return p;
  }
  function partnerFlags(res) { /* "plays you in week N": a trade that helps them that week is a trade against yourself */
    return (res.games || []).filter(function (g) { return g.is_partner; }).map(function (g) {
      var d = res.their ? res.their[g.week] : null;
      var tail = !isNum(d) ? "" : d >= 0.05 ? ": this trade adds " + d.toFixed(1) + " to their week " + g.week : d <= -0.05 ? ": this trade takes " + Math.abs(d).toFixed(1) + " off their week " + g.week : ": their week " + g.week + " does not change";
      return el("p", {class: "fw-flag", "data-dir": isNum(d) && d >= 0.05 ? "up" : "flat"}, el("b", {text: res.partner}), " plays you in week " + g.week + tail + ".");
    });
  }
  function block(res, sig) {
    var box = el("div", {class: "fw-enrich", "data-fw": sig, role: "group", "aria-label": "Weekly numbers for your games left"});
    if (!res) { box.appendChild(el("p", {class: "fw-line fw-wait", text: "Weekly numbers: working…"})); return box; }
    if (res.why) { box.appendChild(el("p", {class: "fw-line"}, "Weekly numbers: ", na(res.why), " (" + res.why + ")")); return box; }
    box.appendChild(headLine(res));
    if (res.kind === "offer") partnerFlags(res).forEach(function (f) { box.appendChild(f); });
    box.appendChild(chipsOf(res.weeks, res.delta, res.games));
    if (res.kind === "pickup") {
      if (res.assumedDrop) box.appendChild(el("p", {class: "fw-rivals", text: "The card names no drop, so these numbers drop " + res.assumedDrop + ", your cheapest drop by weekly projections."}));
      box.appendChild(rivalsLine(res));
    }
    return box;
  }
  function sortValue(res) { var v = res && !res.why ? (state.usd ? res.dollars : res.total) : null; return isNum(v) ? v : null; }
  function apply(card, job) {
    var done = Object.prototype.hasOwnProperty.call(state.cache, job.sig), res = done ? state.cache[job.sig] : null;
    var want = (done ? "" : "wait:") + job.sig, old = card.querySelector(".fw-enrich");
    if (old && old.getAttribute("data-fw") === want) return done;
    if (old) old.remove();
    var main = card.querySelector(".pk-main") || card, why = main.querySelector("details.why");
    main.insertBefore(block(res, want), why && why.parentNode === main ? why : null); /* above the live "Why", below the live notes */
    var v = sortValue(res);
    if (v === null) card.removeAttribute("data-fw-value"); else card.setAttribute("data-fw-value", String(v));
    if (!done && !state.queued[job.sig]) { state.queued[job.sig] = true; state.queue.push(job); }
    return done;
  }

  /* ---------- sort: our option in the live control, the cards reordered inside each live list ---------- */
  function sortSelect() { return document.getElementById("sort"); }
  function ourSort() { var s = sortSelect(); return !!s && s.value === SORT_VALUE; }
  function addSortOption() {
    var sel = sortSelect();
    if (!sel || sel.querySelector('option[value="' + SORT_VALUE + '"]')) return;
    sel.insertBefore(el("option", {value: SORT_VALUE, text: state.usd ? "Games left (expected $)" : "Games left (weekly points)"}), sel.firstChild);
    var note = document.getElementById("sort-note");
    if (note) note.appendChild(el("span", {"data-fw-note": "", text: " For your games left: " + (state.usd ? "expected prize money from weekly projections, each week's points priced by what that game is worth to your season." : "the projected points a move adds to your best lineup over the weeks left.") + " It orders the offers listed in each section, and the waiver pickups."}));
    sel.value = SORT_VALUE; /* the default while the league is connected (framework 3d) */
    sel.dispatchEvent(new Event("change", {bubbles: true})); /* the live page redraws: its Sort chip now names this option */
    var reset = document.getElementById("reset"); /* the live Reset goes back to the live default; ours is the default here */
    if (reset) reset.addEventListener("click", function () { sel.value = SORT_VALUE; sel.dispatchEvent(new Event("change", {bubbles: true})); });
  }
  function reorder(box) {
    var cards = [].filter.call(box.children, function (c) { return c.matches("[data-offer],[data-pickup]"); });
    if (cards.length < 2 || cards.some(function (c) { var b = c.querySelector(".fw-enrich"); return !b || /^wait:/.test(b.getAttribute("data-fw")); })) return;
    var val = function (c) { var v = c.getAttribute("data-fw-value"); return v === null ? -Infinity : +v; };
    var sorted = cards.map(function (c, i) { return {c: c, i: i, v: val(c)}; }).sort(function (a, b) { return b.v - a.v || a.i - b.i; }); /* no number: last, in the live order */
    if (sorted.every(function (x, i) { return x.c === cards[i]; })) return;
    var focus = document.activeElement && box.contains(document.activeElement) ? document.activeElement : null;
    sorted.forEach(function (x) { x.c.classList.add("fw-moved"); box.appendChild(x.c); });
    if (focus) focus.focus();
  }

  /* ---------- one pass over the live cards: safe to run any number of times ---------- */
  var observer = null;
  function pass() {
    if (!state.plan) return;
    var pending = 0, best = null;
    [].forEach.call(document.querySelectorAll("[data-offer]"), function (card) {
      var job = offerJob(card);
      if (!apply(card, job)) { pending++; return; }
      var res = state.cache[job.sig], v = sortValue(res);
      if (v !== null && v > 0 && (!best || v > best.v)) best = {v: v, res: res, sig: job.sig};
    });
    [].forEach.call(document.querySelectorAll("[data-pickup]"), function (card) { if (!apply(card, pickupJob(card))) pending++; });
    if (ourSort()) [].forEach.call(document.querySelectorAll(".find-page .pkgs"), reorder);
    if (!pending) setBest(best);
    if (observer) observer.takeRecords(); /* our own writes are not a redraw */
    if (state.queue.length && !state.running) { state.running = true; work(); }
  }
  /* The numbers: a screen of cards is worked out at once (under a millisecond per offer), so the block and the order are
     there before the cards paint. A long list (Show 200) goes on in short turns so the page stays responsive. */
  function work() {
    var until = Date.now() + 40;
    while (state.queue.length && Date.now() < until) {
      var job = state.queue.shift(), res;
      try { res = job.run(); } catch (e) { res = {why: "the weekly numbers could not be worked out: " + String((e && e.message) || e)}; }
      state.cache[job.sig] = res; delete state.queued[job.sig];
    }
    if (state.queue.length) { setTimeout(work, 0); return; }
    state.running = false;
    pass();
  }
  function watch() {
    var page = document.querySelector("main.find-page") || document.querySelector("main");
    if (!page || observer) return;
    var mine = function (n) { return n && n.nodeType === 1 && (n.closest("#fw-root") || n.closest(".fw-enrich")); };
    observer = new MutationObserver(function (recs) {
      if (recs.every(function (r) { return mine(r.target); })) return;
      pass();
    });
    observer.observe(page, {childList: true, subtree: true});
  }

  /* ---------- panel 1: Your moves, in time order ---------- */
  /* The trade line is the live offer card with the highest expected $ (the cards listed below), by the trade deadline. */
  function tradeMove() {
    var dl = state.data.summary.settings && state.data.summary.settings.trade_deadline, b = state.best;
    if (!b || !dl || !dl.date) return [];
    var r = b.res;
    return [{week: null, kind: "trade", when: "by " + dl.date + " (trade deadline)", when_sort: 0, gain: r.total,
      text: "Trade window: best offer below, " + r.give.join(" and ") + " for " + r.get.join(" and ") + " with " + r.partner + (state.usd ? " (" + dollarText(r.dollars) + " expected for your games left)" : "")}];
  }
  function setBest(best) { /* redraw the panel only when the best offer changes */
    var sig = best ? best.sig : null;
    if (sig === state.bestSig) return;
    state.best = best; state.bestSig = sig;
    if (state.movesBox) renderMoves(state.movesBox);
  }
  function movesList() {
    /* The planner aims an add at each game it helps; one line per player, at its first deadline. */
    var idOf = {};
    state.plan.games.forEach(function (g) { (g.moves || []).forEach(function (m) { if (m.kind === "add" && m.player_id) idOf[g.week + "|" + m.text] = m.player_id; }); });
    var seen = {}, out = [];
    state.moves.concat(tradeMove()).sort(function (a, b) { return a.when_sort - b.when_sort; }).forEach(function (m) {
      var pid = m.kind === "add" ? idOf[m.week + "|" + m.text] : null;
      if (pid && seen[pid]) { seen[pid].also.push(m.week); return; }
      var row = {m: m, also: []};
      if (pid) seen[pid] = row;
      out.push(row);
    });
    return out;
  }
  function renderMoves(box) {
    box.textContent = "";
    box.appendChild(el("h2", {id: "fw-moves-h", text: "Your moves, in time order"}));
    var rows = movesList();
    if (!rows.length) { box.appendChild(el("p", {class: "muted", text: "No timed moves right now: your best lineup is set, no available player adds a point or more in any game left, and no offer listed below adds to your games left."})); return; }
    box.appendChild(el("p", {class: "muted", text: "What to do and by when, from weekly projections for the games you have left. The first deadline comes first."}));
    var ol = el("ol", {class: "fw-movelist"});
    rows.forEach(function (r, i) {
      var m = r.m, gainText = isNum(m.gain) ? pts(m.gain) : null;
      var scope = m.kind === "trade" ? "over the weeks left" : m.week != null ? "in week " + m.week : "";
      var li = el("li", {hidden: !state.showAllMoves && i >= MOVES_SHOWN},
        el("span", {class: "fw-when", text: dates(m.when)}),
        el("span", {class: "fw-kind", "data-kind": m.kind, text: KINDS[m.kind] || m.kind}),
        el("span", {class: "fw-what"}, el("span", {text: dates(m.text)}),
          r.also.length ? el("small", {text: "Also helps week" + (r.also.length > 1 ? "s " : " ") + r.also.join(", ") + "."}) : null),
        el("span", {class: "fw-gain"}, gainText ? el("b", {"data-dir": m.gain > 0 ? "up" : m.gain < 0 ? "down" : "flat", text: gainText}) : na("The planner has no point figure for this move"),
          scope ? el("small", {text: scope}) : null));
      ol.appendChild(li);
    });
    box.appendChild(ol);
    if (rows.length > MOVES_SHOWN) box.appendChild(el("button", {type: "button", class: "fw-more", "aria-expanded": String(state.showAllMoves),
      text: state.showAllMoves ? "Show fewer" : "Show all " + rows.length + " moves", onclick: function () { state.showAllMoves = !state.showAllMoves; renderMoves(box); }}));
  }

  /* who else this pickup helps, with their FAAB and waiver priority: context for a bid, never a bid */
  function rivalsLine(a) {
    var team = (state.data.summary.teams || []).filter(function (t) { return t.team_key === myKey(); })[0] || {};
    var num = function (x) { return x === null || x === undefined || x === "" || !isFinite(+x) ? null : +x; };
    var me = {faab: num(team.faab_remaining), waiver_priority: num(team.waiver_priority)}, rv = a.rivals || [];
    var st = ((window.DDFStaging && window.DDFStaging.summary) || {}).settings || {}, noFaab = st.waiver_type && st.waiver_type !== "faab";
    var money = function (x) { return isNum(x) ? "$" + Math.round(x) : noFaab ? "no FAAB" : "FAAB unknown"; };
    var mine = "You have " + money(me.faab) + (isNum(me.waiver_priority) ? ", waiver priority " + me.waiver_priority : "") + ".";
    if (!rv.length) return el("p", {class: "fw-rivals", text: "No other team's lineup gains a point or more from him. " + mine});
    /* a rival's gain is before any drop (yours counts your cheapest drop), so the line says so */
    return el("p", {class: "fw-rivals", text: "Also helps, before any drop: " + rv.map(function (r) {
      return r.name + " " + (isNum(r.gain) ? "+" + r.gain.toFixed(1) : "— (" + (r.why || "a week has no projection") + ")") + " (" + money(r.faab) + (isNum(r.waiver_priority) ? ", priority " + r.waiver_priority : "") + ")";
    }).join("; ") + ". " + mine});
  }
  /* ---------- mount ---------- */
  function mount() {
    var main = document.querySelector("main.find-page") || document.querySelector("main") || document.body;
    var old = document.getElementById("fw-root"); if (old) old.remove();
    var root = el("div", {id: "fw-root", class: "fw"});
    /* above the live filters, below the page title and its notes */
    var anchor = main.querySelector(".pw-flagrow") || main.querySelector(".find-chiprow") || main.querySelector("#find-filters");
    if (anchor && anchor.parentNode === main) main.insertBefore(root, anchor); else main.insertBefore(root, main.children[1] || null);
    return root;
  }
  function message(root, strong, text) { root.textContent = ""; root.appendChild(el("div", {class: "flag fw-msg", role: "status"}, el("strong", {text: strong}), " " + text)); }
  function start(data) {
    var root = mount();
    if (!W) return message(root, "Weekly planner did not load.", "Your moves and the weekly numbers on the cards need weekly.js. The rest of the page is not affected.");
    if (!data || !data.summary) return message(root, "No stored league.", "Your moves and the weekly numbers on the cards need your connected league.");
    if (!data.weekly) return message(root, "Weekly projections are not available.", ((window.DDFStaging && DDFStaging.weeklyError) || "The weekly read failed.") + " Your moves and the weekly numbers on the cards need them; the rest of the page is not affected.");
    state.data = data;
    message(root, "Working out your moves…", "Reading weekly projections for the games you have left.");
    setTimeout(function () {
      try {
        state.plan = W.plan(data.summary, data.weekly, {});
        state.usd = state.plan.games.some(function (g) { return isNum(g.dollars_per_point); });
        /* the planner's timed moves; its own trade ideas are not used (no acceptance test is passed, so it offers none) */
        state.moves = W.recommendations(data.summary, data.weekly, myKey(), {plan: state.plan}).moves_in_time.filter(function (m) { return m.kind !== "trade"; });
      } catch (e) { state.plan = null; return message(root, "Your moves could not be worked out.", String((e && e.message) || e)); }
      root.textContent = "";
      state.movesBox = el("section", {class: "card fw-moves", "aria-labelledby": "fw-moves-h"});
      root.appendChild(state.movesBox);
      root.appendChild(el("p", {class: "muted fw-below", text: "On the offer and pickup cards below, the “" + (state.usd ? "Expected $, your games left" : "Weekly points, your games left") + "” lines come from weekly projections only, never DDF Value. Each chip is one week left: points gained in your best lineup, and the change in your win chance where the opponent is known." + (data.mock ? " Sample data: an invented league." : "")}));
      renderMoves(state.movesBox);
      addSortOption(); watch(); pass();
    }, 30);
  }

  var S = window.DDFStaging;
  if (S && S.ready && typeof S.ready.then === "function") S.ready.then(function (d) { start({summary: d.summary, weekly: d.weekly, mock: false}); });
  else if (MOCK) { /* local preview without the bridge: an invented league, the moves panel only (no live cards to enrich) */
    fetch(new URL("plan-sample-find.json", SELF || location.href)).then(function (r) { return r.json(); })
      .then(function (d) { start({summary: d.summary, weekly: d.weekly, mock: true}); })
      .catch(function () { message(mount(), "Sample data did not load.", "plan-sample-find.json is served by the local harness only."); });
  }
})();
