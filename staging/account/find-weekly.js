/* DDF staging: Trade & Waiver Recommendations by weekly gain (JEG-1736, piece 3).
 * Loaded by league-bridge.js (data-add) after the live find page is in the document. Adds two panels above the live
 * filters and leaves every live section as it is:
 *   1. "Your moves, in time order"      DDFWeekly.recommendations(...).moves_in_time
 *   2. "By weekly gain"                 adds and one-for-one trades, Sort "For your games left" (default) or
 *                                       "Weekly points over the weeks left"
 * Weekly projections only, never DDF Value. A missing value is never 0: null renders as "—" with its reason.
 * Every league string is written with textContent, never as HTML. */
(function () {
  "use strict";
  var QS = new URLSearchParams(location.search);
  var IS_LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  var MOCK = IS_LOCAL && QS.get("mock") === "1"; /* sample league, local preview only */
  var SELF = document.currentScript && document.currentScript.src;
  var W = window.DDFWeekly;
  var SORTS = [["games", "For your games left"], ["points", "Weekly points over the weeks left"]];
  var SORT_NOTE = {
    games: "Each week's gain counts by what that game is worth to your season: how far a win moves your playoff and seed chances. Playoff weeks count in full.",
    points: "The plain sum of projected points gained in your best lineup over the weeks left."
  };
  var TYPES = {must_win: "Must-win", bankable: "Bankable", favored: "Favored", seed_game: "Seed game", free: "Free", playoff: "Playoff"};
  var KINDS = {start: "Start", add: "Add", watch: "Watch", trade: "Trade"};
  var MOVES_SHOWN = 6, CARDS_SHOWN = 5;
  var state = {data: null, plan: null, sort: "games", rec: null, impact: {}, showAllMoves: false, showAll: {adds: false, trades: false}};

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
  function addChips(a) { /* a waiver add: my lineup moves, the opponent's does not */
    var sd = state.plan.spread && state.plan.spread.sd, ul = el("ul", {class: "fw-chips", "aria-label": "Gain by week"});
    state.rec.weeks.forEach(function (w) {
      var gain = a.gain_by_week[w], g = gameOf(w), win = null, why = null;
      var sdw = (state.plan.spreads || {})[w] || sd; /* the same spread the game's own win chance used */
      if (isNum(gain) && g && g.opp && isNum(g.margin) && isNum(g.win && g.win.ddf) && isNum(sdw)) win = winDelta(g.win.ddf, W.winChance(g.margin + gain, sdw));
      else if (g && !g.opp) why = g.opp_note || "Opponent not set yet, so no win chance";
      ul.appendChild(chip(w, gain, win, why));
    });
    return ul;
  }
  function impactOf(t) { /* both sides by week for one trade (DDFWeekly.tradeImpact), worked out once per trade */
    var id = t.partner_key + "|" + t.give[0].player_id + "|" + t.get[0].player_id;
    if (!(id in state.impact)) {
      try { state.impact[id] = W.tradeImpact(state.data.summary, state.data.weekly, state.plan.me.team_key, t.partner_key, [t.give[0].player_id], [t.get[0].player_id], {sd: state.plan.spread && state.plan.spread.sd}); }
      catch (e) { state.impact[id] = null; }
    }
    return state.impact[id];
  }
  function tradeChips(t, imp) {
    var ul = el("ul", {class: "fw-chips", "aria-label": "Your gain by week"});
    state.rec.weeks.forEach(function (w) {
      var gm = imp ? imp.games.filter(function (x) { return x.week === w; })[0] : null, g = gameOf(w);
      var win = gm ? winDelta(gm.win_before, gm.win_after) : null;
      ul.appendChild(chip(w, t.my_gain_by_week[w], win, !win && g && !g.opp ? (g.opp_note || "Opponent not set yet, so no win chance") : null));
    });
    return ul;
  }

  /* ---------- panel 1: Your moves, in time order ---------- */
  function movesList() {
    /* The planner aims an add at each game it helps; one line per player, at its first deadline. */
    var idOf = {};
    state.plan.games.forEach(function (g) { (g.moves || []).forEach(function (m) { if (m.kind === "add" && m.player_id) idOf[g.week + "|" + m.text] = m.player_id; }); });
    var seen = {}, out = [];
    state.rec.moves_in_time.forEach(function (m) {
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
    if (!rows.length) { box.appendChild(el("p", {class: "muted", text: "No timed moves right now: your best lineup is set and no available player adds a point or more in any game left."})); return; }
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

  /* ---------- panel 2: by weekly gain ---------- */
  function gainCell(value, label, sub) {
    return el("div", {class: "pk-gain"}, el("small", {text: label}),
      isNum(value) ? el("b", {class: "gain", text: signed(value)}) : el("b", {class: "gain"}, na("A starter has no projection in one of the weeks left")),
      sub ? el("small", {class: "pk-total", text: sub}) : null);
  }
  function headline(item, kind) { /* the number the sort ranks by, and the other one beside it */
    var total = kind === "add" ? item.total_gain : item.my_total, weighted = kind === "add" ? item.weighted_gain : item.my_weighted;
    return state.sort === "games"
      ? gainCell(weighted, "For your games left", isNum(total) ? pts(total) + " over the weeks left" : null)
      : gainCell(total, "Weekly points, weeks left", isNum(weighted) ? signed(weighted) + " for your games left" : null);
  }
  /* who else this pickup helps, with their FAAB and waiver priority: context for a bid, never a bid */
  function rivalsLine(a) {
    var me = (state.rec && state.rec.me) || {}, rv = a.rivals || [];
    var money = function (x) { return isNum(x) ? "$" + Math.round(x) : "FAAB unknown"; };
    var mine = "You have " + money(me.faab) + (isNum(me.waiver_priority) ? ", waiver priority " + me.waiver_priority : "") + ".";
    if (!rv.length) return el("p", {class: "fw-rivals", text: "No other team's lineup gains a point or more from him. " + mine});
    return el("p", {class: "fw-rivals", text: "Also helps: " + rv.map(function (r) {
      return r.name + " +" + r.gain.toFixed(1) + " (" + money(r.faab) + (isNum(r.waiver_priority) ? ", priority " + r.waiver_priority : "") + ")";
    }).join("; ") + ". " + mine});
  }
  function addCard(a) {
    return el("article", {class: "pkg fw-card", "data-fw-add": a.player_id},
      el("div", {class: "pk-main"},
        el("div", {class: "pk-ex"},
          el("div", {class: "pk-side"}, el("small", {text: "You drop"}), el("b", {text: a.drop ? a.drop.name : "Nobody (open roster spot)"})),
          el("span", {class: "pk-arrow", "aria-hidden": "true", text: "→"}),
          el("div", {class: "pk-side"}, el("small", {text: "You add"}), el("b", {text: a.name + " · " + a.pos}))),
        /* the league data does not say waivers or free agent, so the tag says only that he is on no roster */
        el("div", {class: "pk-meta"}, el("span", {class: "ptag wv", text: "Available"}),
          a.status ? el("span", {class: "ptag", text: a.status}) : null,
          isNum(a.percent_owned) ? el("span", {class: "fit", text: "Rostered in " + Math.round(a.percent_owned) + "%"}) : null),
        addChips(a), rivalsLine(a)),
      headline(a, "add"));
  }
  function staging(page) { var S = window.DDFStaging; return S && typeof S.url === "function" ? S.url(page) : null; } /* the staging copy of a page */
  function buildHref(t) { /* the live Build a Trade link for this swap, when both players matched to DDF */
    try {
      var S = window.DDFStaging, key = {};
      ((S && S.matched && S.matched.teams) || []).forEach(function (tm) { (tm.players || []).forEach(function (p) { key[p.player_id] = p.key; }); });
      var gv = t.give.map(function (p) { return {key: key[p.player_id], n: p.name}; }), gt = t.get.map(function (p) { return {key: key[p.player_id], n: p.name}; });
      if (gv.concat(gt).some(function (p) { return !p.key; }) || !window.DDF || !DDF.engine || !DDF.engine.buildHref) return null;
      var href = DDF.engine.buildHref({partner: t.partner_name, give: gv, get: gt}), local = staging("build.html");
      if (!local) return href;
      var lg = S.league && S.league.id ? "league=" + encodeURIComponent(S.league.id) : "";
      href = href.replace(/^[^?#]*/, local);
      return lg ? href.replace(/(#|$)/, (href.indexOf("?") >= 0 ? "&" : "?") + lg + "$1") : href;
    } catch (e) { return null; }
  }
  function tradeCard(t) {
    var imp = impactOf(t), wk = t.partner_plays_me_week, href = buildHref(t), flag = null;
    if (wk != null) {
      var d = imp && imp.sides[1] ? imp.sides[1].delta[wk] : null;
      var tail = !isNum(d) ? "" : d >= 0.05 ? ": this trade adds " + d.toFixed(1) + " to their week " + wk : d <= -0.05 ? ": this trade takes " + Math.abs(d).toFixed(1) + " off their week " + wk : ": their week " + wk + " does not change";
      flag = el("p", {class: "fw-flag", "data-dir": isNum(d) && d >= 0.05 ? "up" : "flat"}, el("b", {text: t.partner_name}), " plays you in week " + wk + tail + ".");
    }
    return el("article", {class: "pkg fw-card", "data-fw-trade": t.partner_key},
      el("div", {class: "pk-main"},
        el("div", {class: "pk-ex"},
          el("div", {class: "pk-side"}, el("small", {text: "You give"}), el("b", {text: t.give.map(function (p) { return p.name + " · " + p.pos; }).join(", ")})),
          el("span", {class: "pk-arrow", "aria-hidden": "true", text: "→"}),
          el("div", {class: "pk-side"}, el("small", {text: "You get"}), el("b", {text: t.get.map(function (p) { return p.name + " · " + p.pos; }).join(", ")}))),
        el("div", {class: "pk-meta"}, el("span", {class: "ptag", title: "Trading partner: " + t.partner_name}, "Trade with ", el("b", {text: t.partner_name})),
          el("span", {class: "fit"}, "Their lineup ", isNum(t.their_total) ? pts(t.their_total) + " over the weeks left" : na("A starter of theirs has no projection in one of the weeks left"))),
        flag, tradeChips(t, imp)),
      headline(t, "trade"),
      href ? el("div", {class: "pk-act"}, el("a", {class: "button", href: href}, "Build a Trade ", el("span", {class: "arr", "aria-hidden": "true", text: "→"}))) : null);
  }
  function more(kind, n, rerender) {
    return el("button", {type: "button", class: "fw-more", "aria-expanded": String(state.showAll[kind]),
      text: state.showAll[kind] ? "Show fewer" : "Show all " + n, onclick: function () { state.showAll[kind] = !state.showAll[kind]; rerender(); }});
  }
  function sortKey(a, kind) { var v = kind === "add" ? (state.sort === "games" ? a.weighted_gain : a.total_gain) : (state.sort === "games" ? a.my_weighted : a.my_total); return isNum(v) ? v : -Infinity; }
  function renderAdds(box) {
    box.textContent = "";
    var adds = state.rec.adds, fas = (state.data.summary.free_agents || []).length;
    box.appendChild(el("h3", {}, "Waiver pickups ", el("small", {class: "cnt", text: String(adds.length)})));
    if (!adds.length) { box.appendChild(el("p", {class: "empty", text: fas ? "No available player adds half a point or more to your best lineup over the weeks left." : "No available players in the stored league data, so no pickups can be ranked."})); return; }
    box.appendChild(el("p", {class: "def", text: "Grouped by the game each pickup helps most. The drop is the player whose loss costs your lineups least over the weeks left."}));
    /* group by the game the pickup helps most (the earliest on a tie); groups in week order, the Sort order inside */
    var groups = {}, order = [];
    adds.forEach(function (a) {
      var w = state.rec.weeks[0], best = -Infinity;
      state.rec.weeks.forEach(function (x) { var v = a.gain_by_week[x]; if (isNum(v) && v > best) { best = v; w = x; } });
      if (!groups[w]) { groups[w] = []; order.push(w); }
      groups[w].push(a);
    });
    order.sort(function (a, b) { return a - b; });
    var shown = 0, limit = state.showAll.adds ? Infinity : CARDS_SHOWN;
    order.forEach(function (w) {
      if (shown >= limit) return;
      var list = groups[w].slice().sort(function (a, b) { return sortKey(b, "add") - sortKey(a, "add"); }).slice(0, limit - shown);
      shown += list.length;
      var g = gameOf(w), type = g && g.type ? TYPES[g.type] || null : null;
      box.appendChild(el("h4", {class: "fw-game"}, el("span", {text: gameLabel(w)}), type ? el("small", {text: type}) : null));
      var cards = el("div", {class: "pkgs"}); list.forEach(function (a) { cards.appendChild(addCard(a)); }); box.appendChild(cards);
    });
    if (adds.length > CARDS_SHOWN) box.appendChild(more("adds", adds.length, function () { renderAdds(box); }));
  }
  function renderTrades(box) {
    box.textContent = "";
    var trades = state.rec.trades;
    box.appendChild(el("h3", {}, "Trades, one for one ", el("small", {class: "cnt", text: String(trades.length)})));
    if (!trades.length) { box.appendChild(el("p", {class: "empty", text: "No one-for-one swap adds 2 points or more to your lineups over the weeks left without costing the other team more than a point."})); return; }
    box.appendChild(el("p", {class: "def", text: "Your best lineups gain 2 points or more over the weeks left, and theirs lose no more than 1. K and DEF are left out."}));
    var cards = el("div", {class: "pkgs"});
    trades.slice(0, state.showAll.trades ? trades.length : CARDS_SHOWN).forEach(function (t) { cards.appendChild(tradeCard(t)); });
    box.appendChild(cards);
    if (trades.length > CARDS_SHOWN) box.appendChild(more("trades", trades.length, function () { renderTrades(box); }));
  }
  function sourcesLine() {
    var p = el("p", {class: "muted fw-src"});
    var lines = (state.plan.sources || []).filter(function (s) { return /^(Player projections|K and DEF|Win chance|Every weekly number|Your league's scoring)/.test(s); });
    p.textContent = "Sources. " + lines.join(" ") + " These panels use weekly projections only, never DDF Value." + (state.data.mock ? " Sample data: an invented league." : "");
    return p;
  }
  function compute() {
    state.rec = W.recommendations(state.data.summary, state.data.weekly, state.plan.me.team_key, {plan: state.plan, sort: state.sort === "games" ? "games" : "points"});
  }
  function renderWeekly(sec, movesBox) {
    sec.textContent = "";
    var note = el("span", {role: "note", id: "fw-sort-note", text: SORT_NOTE[state.sort]});
    var sel = el("select", {id: "fw-sort", "aria-describedby": "fw-sort-note"});
    SORTS.forEach(function (s) { var o = el("option", {value: s[0], text: s[1]}); if (s[0] === state.sort) o.selected = true; sel.appendChild(o); });
    var adds = el("div", {class: "fw-block", id: "fw-adds"}), trades = el("div", {class: "fw-block", id: "fw-trades"});
    sel.addEventListener("change", function () {
      state.sort = sel.value; note.textContent = SORT_NOTE[state.sort];
      compute(); renderAdds(adds); renderTrades(trades); renderMoves(movesBox);
    });
    sec.appendChild(el("h2", {id: "fw-weekly-h", text: "By weekly gain"}));
    sec.appendChild(el("p", {class: "def", text: "Pickups and trades ranked by the projected points they add to your best lineup in each week left. Each chip is one week: points gained, and the change in your win chance where the opponent is known."}));
    sec.appendChild(el("div", {class: "fw-sortrow"}, el("label", {for: "fw-sort", text: "Sort"}), sel, note));
    sec.appendChild(adds); sec.appendChild(trades); sec.appendChild(sourcesLine());
    renderAdds(adds); renderTrades(trades);
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
    if (!W) return message(root, "Weekly planner did not load.", "The moves and weekly-gain panels need weekly.js. The sections below are not affected.");
    if (!data || !data.summary) return message(root, "No stored league.", "The moves and weekly-gain panels need your connected league.");
    if (!data.weekly) return message(root, "Weekly projections are not available.", ((window.DDFStaging && DDFStaging.weeklyError) || "The weekly read failed.") + " The moves and weekly-gain panels need them; the sections below are not affected.");
    state.data = data;
    message(root, "Working out your moves…", "Reading weekly projections for the games you have left.");
    setTimeout(function () {
      try {
        state.plan = W.plan(data.summary, data.weekly, {});
        compute();
      } catch (e) { return message(root, "Your moves could not be worked out.", String((e && e.message) || e)); }
      root.textContent = "";
      var movesBox = el("section", {class: "card fw-moves", "aria-labelledby": "fw-moves-h"});
      var sec = el("section", {class: "section fw-weekly", "aria-labelledby": "fw-weekly-h"});
      root.appendChild(movesBox); root.appendChild(sec);
      root.appendChild(el("p", {class: "muted fw-below", text: "Below: the offers and pickups ranked on DDF Value, as on the live page."}));
      renderMoves(movesBox); renderWeekly(sec, movesBox);
    }, 30);
  }

  var S = window.DDFStaging;
  if (S && S.ready && typeof S.ready.then === "function") S.ready.then(function (d) { start({summary: d.summary, weekly: d.weekly, mock: false}); });
  else if (MOCK) { /* local preview without the bridge: an invented league */
    fetch(new URL("plan-sample-find.json", SELF || location.href)).then(function (r) { return r.json(); })
      .then(function (d) { start({summary: d.summary, weekly: d.weekly, mock: true}); })
      .catch(function () { message(mount(), "Sample data did not load.", "plan-sample-find.json is served by the local harness only."); });
  }
})();
