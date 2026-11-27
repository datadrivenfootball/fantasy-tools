/* Build a Trade on staging (JEG-1736, piece 4): two panels below "Starting lineup after this trade".
 *   Week by week, both sides  each team's best lineup per week before and after the trade, and my game that week
 *                             (win chance before and after; a game against the trade partner counts twice).
 *   Player by player          each moving player's projection per week and whether he starts for the team that ends
 *                             up with him.
 * Weekly projections only (DDFWeekly.tradeImpact, weekly.js); no DDF Value is read or shown here.
 *
 * Loaded by league-bridge.js after the live page's own scripts. The live scripts are not edited: the current trade is
 * read from window.DDFBuild (build-trade.js: state(), picked(side), league(), rec(key)) and the panels redraw when the
 * live page redraws its own "You give / You get" boxes and lineup card.
 * Players are mapped to the stored league by DDFStaging.matched (engine key -> stored player_id on that team's stored
 * roster); a player the stored rosters do not have is named and the panels show no numbers.
 */
(function () {
  "use strict";
  var ST = window.DDFStaging, W = window.DDFWeekly;
  if (!ST || !ST.ready || !W) return;

  // ---------- small DOM helpers (textContent only) ----------
  function el(tag, attrs) {
    var n = document.createElement(tag), k, i, c;
    for (k in (attrs || {})) {
      if (attrs[k] == null || attrs[k] === false) continue;
      if (k === "text") n.textContent = attrs[k]; else if (k === "class") n.className = attrs[k]; else n.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    }
    for (i = 2; i < arguments.length; i++) { c = arguments[i]; if (c != null && c !== false) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    return n;
  }
  var isNum = function (x) { return typeof x === "number" && isFinite(x); };
  var norm = function (s) { return String(s || "").toLowerCase().replace(/[.'’`]/g, "").replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "").replace(/[^a-z0-9]+/g, " ").trim(); };
  var signed = function (x) { return Math.abs(x) < 0.05 ? "0.0" : (x > 0 ? "+" : "−") + Math.abs(x).toFixed(1); };
  var dir = function (x) { return !isNum(x) || Math.abs(x) < 0.05 ? "flat" : x > 0 ? "up" : "down"; };
  var joinNames = function (l) { return l.length < 3 ? l.join(" and ") : l.slice(0, -1).join(", ") + " and " + l[l.length - 1]; };

  // "—" always carries its reason: as a tooltip, for screen readers, and as a numbered line under the table (phones).
  function Notes() { this.list = []; }
  Notes.prototype.na = function (reason) {
    var r = reason || "Not available", i = this.list.indexOf(r);
    if (i < 0) { this.list.push(r); i = this.list.length - 1; }
    return el("span", {class: "bw-na", title: r, "aria-label": "Not available: " + r}, "—", el("sup", {text: String(i + 1), "aria-hidden": "true"}));
  };
  Notes.prototype.node = function () {
    if (!this.list.length) return null;
    var ol = el("ol", {class: "bw-notes"});
    this.list.forEach(function (r) { ol.appendChild(el("li", {text: r})); });
    return ol;
  };

  // ---------- the live trade -> stored league ids ----------
  function storedTeam(ctx, liveTeam) {
    var m = ST.matched && ST.matched.teams ? ST.matched.teams[Number(liveTeam.id)] : null;
    var teams = ctx.summary.teams || [];
    var t = m ? teams.filter(function (x) { return x.team_key === m.team_key; })[0] : null;
    if (!t) { // no bridge map: the stored team of the same name, only when exactly one has it
      var same = teams.filter(function (x) { return norm(x.name) === norm(liveTeam.name); });
      t = same.length === 1 ? same[0] : null;
    }
    if (!t) return null;
    var byKey = {};
    ((m && m.players) || []).forEach(function (p) { if (p && p.key != null && p.player_id != null) byKey[String(p.key)] = p.player_id; });
    return {team: t, byKey: byKey};
  }
  function storedId(side, key, rec) {
    var has = function (id) { return side.team.roster.some(function (e) { return e.player_id === id; }); };
    if (side.byKey[String(key)] != null && has(side.byKey[String(key)])) return side.byKey[String(key)];
    // fall back to the stored roster itself: same name, and the same position when two share it
    var n = norm(rec && rec.n), hits = side.team.roster.filter(function (e) { return norm(e.name) === n; });
    if (hits.length > 1 && rec && rec.pos) hits = hits.filter(function (e) { return String(e.position || e.pos || "").toUpperCase().indexOf(rec.pos) >= 0; });
    return hits.length === 1 ? hits[0].player_id : null;
  }
  /* What the live page shows now. null = the panels do not apply (waivers, "Any players", no partner, nothing picked). */
  function liveTrade() {
    var B = window.DDFBuild; if (!B) return null;
    var s = B.state(), L = B.league();
    if (!s || !L || s.kind !== "trade" || s.mode !== "league" || !L.available || L.me < 0 || !(s.partner >= 0) || !L.teams[s.partner]) return null;
    var give = B.picked("give"), get = B.picked("get");
    if (!give.length && !get.length) return null;
    return {me: L.teams[L.me], partner: L.teams[s.partner], give: give, get: get, rec: B.rec,
      sig: [L.me, s.partner, give.join(","), get.join(",")].join("|")};
  }
  function impact(ctx, t) {
    if (!ctx.weekly) return {error: "Weekly projections did not load" + (ST.weeklyError ? " (" + ST.weeklyError + ")" : "") + ". Reload the page to try again."};
    var mine = storedTeam(ctx, t.me), theirs = storedTeam(ctx, t.partner);
    if (!mine || !theirs) return {error: "These panels need both teams from your connected league, and " + (!mine ? t.me.name : t.partner.name) + " was not found in it."};
    var lost = [];
    var ids = function (keys, side) {
      return keys.map(function (k) { var r = t.rec(k), id = storedId(side, k, r); if (id == null) lost.push((r && r.n) || String(k)); return id; });
    };
    var giveIds = ids(t.give, mine), getIds = ids(t.get, theirs);
    if (lost.length) return {error: joinNames(lost) + (lost.length === 1 ? " is" : " are") + " not on these two rosters in your connected league, so there are no weekly numbers for this trade."};
    try { return {data: W.tradeImpact(ctx.summary, ctx.weekly, mine.team.team_key, theirs.team.team_key, giveIds, getIds), myKey: mine.team.team_key}; }
    catch (e) { return {error: "The weekly numbers could not be worked out for this trade (" + (e && e.message ? e.message : "error") + ")."}; }
  }

  // ---------- Week by week, both sides ----------
  function weekHead(weeks, last) {
    var tr = el("tr", null, el("th", {scope: "col", class: "bw-lab"}, el("span", {class: "bw-sr", text: "Row"})));
    weeks.forEach(function (w) { tr.appendChild(el("th", {scope: "col", class: "bw-num"}, el("small", {text: "WK "}), String(w))); });
    if (last) tr.appendChild(el("th", {scope: "col", class: "bw-num bw-total", text: last}));
    return el("thead", null, tr);
  }
  function sum(map, weeks) { var t = 0, ok = true; weeks.forEach(function (w) { if (isNum(map[w])) t += map[w]; else ok = false; }); return ok ? Math.round(t * 10) / 10 : null; }
  function renderWeeks(body, d, t) {
    var notes = new Notes(), weeks = d.weeks, cols = weeks.length + 2;
    var NO_TOTAL = "A starter has no projection that week, so the lineup has no total";
    var table = el("table", {class: "bw-table"}, el("caption", {class: "bw-sr", text: "Best lineup each week before and after this trade, for both teams, and your game that week"}), weekHead(weeks, "Total"));
    var tb = el("tbody"); table.appendChild(tb);
    var group = function (text, sub) { tb.appendChild(el("tr", {class: "bw-group"}, el("th", {scope: "colgroup", colspan: String(cols)}, text, sub ? el("small", {text: " " + sub}) : null))); };
    var row = function (label, cls, cell, total) {
      var tr = el("tr", {class: cls || null}, el("th", {scope: "row", class: "bw-lab", text: label}));
      weeks.forEach(function (w) { tr.appendChild(cell(w)); });
      tr.appendChild(total || el("td", {class: "bw-num bw-total"}));
      tb.appendChild(tr);
    };
    var numCell = function (v, total) { return el("td", {class: "bw-num" + (total ? " bw-total" : "")}, isNum(v) ? v.toFixed(1) : notes.na(NO_TOTAL)); };
    var deltaCell = function (v, total) { return el("td", {class: "bw-num" + (total ? " bw-total" : ""), "data-dir": dir(v)}, isNum(v) ? signed(v) : notes.na(NO_TOTAL)); };
    d.sides.forEach(function (s, i) {
      group(s.name, i === 0 ? "· your lineup" : "· their lineup");
      row("Before", null, function (w) { return numCell(s.before[w]); }, numCell(sum(s.before, weeks), true));
      row("After", null, function (w) { return numCell(s.after[w]); }, numCell(sum(s.after, weeks), true));
      row("Change", "bw-change", function (w) { return deltaCell(s.delta[w]); }, deltaCell(s.total_delta, true));
    });
    var game = {}; d.games.forEach(function (g) { game[g.week] = g; });
    var NO_OPP = "No opponent set for that week yet", NO_WIN = "No win chance without both lineup totals";
    group("Your game that week");
    row("Opponent", "bw-opp", function (w) {
      var g = game[w] || {};
      if (!g.opp_name) return el("td", {class: "bw-num"}, notes.na(NO_OPP));
      return el("td", {class: "bw-num" + (g.is_partner ? " bw-twice" : "")}, el("span", {class: "bw-oppname", text: g.opp_name}), g.is_partner ? el("span", {class: "bw-chip", text: "counts twice"}) : null);
    });
    var pct = function (v, g) { return isNum(v) ? Math.round(v * 100) + "%" : notes.na(g && g.opp_name ? NO_WIN : NO_OPP); };
    row("Win chance before", null, function (w) { var g = game[w] || {}; return el("td", {class: "bw-num"}, pct(g.win_before, g)); });
    row("Win chance after", "bw-change", function (w) {
      var g = game[w] || {}, both = isNum(g.win_before) && isNum(g.win_after);
      var diff = both ? Math.round(g.win_after * 100) - Math.round(g.win_before * 100) : null;
      return el("td", {class: "bw-num", "data-dir": diff === null || diff === 0 ? "flat" : diff > 0 ? "up" : "down"}, pct(g.win_after, g));
    });
    body.replaceChildren();
    var twice = d.games.filter(function (g) { return g.is_partner; });
    if (twice.length) {
      var wk = joinNames(twice.map(function (g) { return "Week " + g.week; }));
      body.appendChild(el("p", {class: "bw-twice-note"}, el("strong", {text: "You play " + t.partner.name + " in " + wk + ". "}),
        (twice.length === 1 ? "That game counts" : "Those games count") + " twice: the trade changes your lineup and theirs, and the win chance after uses both."));
    }
    body.appendChild(el("div", {class: "bw-scroll", role: "region", tabindex: "0", "aria-label": "Week by week, both sides"}, table));
    var n = notes.node(); if (n) body.appendChild(n);
    body.appendChild(el("p", {class: "muted bw-fine", text: "Each number is the best lineup that team can start that week, on weekly projections."}));
  }

  // ---------- Player by player ----------
  function renderPlayers(body, d, myName) {
    var notes = new Notes(), weeks = d.weeks, cols = weeks.length + 1;
    var table = el("table", {class: "bw-table bw-players"}, el("caption", {class: "bw-sr", text: "Each player in this trade: his projection each week, and whether he starts for the team that ends up with him"}), weekHead(weeks, null));
    var tb = el("tbody"); table.appendChild(tb);
    [["You get", function (p) { return p.to_team === myName; }], ["You give", function (p) { return p.to_team !== myName; }]].forEach(function (g) {
      var list = d.players.filter(g[1]); if (!list.length) return;
      tb.appendChild(el("tr", {class: "bw-group"}, el("th", {scope: "colgroup", colspan: String(cols)}, g[0], el("small", {text: " · would play for " + list[0].to_team}))));
      list.forEach(function (p) {
        var tr = el("tr", null, el("th", {scope: "row", class: "bw-lab"}, el("span", {class: "bw-pname", text: p.name}), el("small", {text: [p.pos, p.nfl_team ? String(p.nfl_team).toUpperCase() : null].filter(Boolean).join(" · ")})));
        weeks.forEach(function (w) {
          var c = p.weeks[w] || {}, td = el("td", {class: "bw-num"});
          if (c.bye) td.appendChild(el("span", {class: "bw-bye", text: "BYE"}));
          else {
            td.appendChild(isNum(c.points) ? el("span", {class: "bw-pts", text: c.points.toFixed(1)}) : notes.na(p.name + ", week " + w + ": " + (c.note || "no projection this week")));
            td.appendChild(el("span", {class: "bw-role", "data-starts": c.starts_after ? "yes" : "no", text: c.starts_after ? "Starts" : "Bench"}));
          }
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
    });
    body.replaceChildren(el("div", {class: "bw-scroll", role: "region", tabindex: "0", "aria-label": "Player by player"}, table));
    var n = notes.node(); if (n) body.appendChild(n);
    body.appendChild(el("p", {class: "muted bw-fine", text: "Weekly projected points. Starts or Bench is for the team that ends up with him after this trade, in that team's best lineup that week."}));
  }

  // ---------- page wiring ----------
  function start(ctx) {
    var anchor = document.getElementById("lineup-card");
    if (!anchor || document.getElementById("bw-weeks")) return;
    var mk = function (id, title) {
      var body = el("div", {id: id + "-body"});
      var sec = el("section", {class: "card bw-card", id: id, "aria-labelledby": id + "-title", hidden: true}, el("h2", {id: id + "-title", text: title}), body);
      return {sec: sec, body: body};
    };
    var weeksP = mk("bw-weeks", "Week by week, both sides"), playersP = mk("bw-players", "Player by player");
    anchor.after(weeksP.sec, playersP.sec);
    var last = null;
    function update() {
      var t = liveTrade(), sig = t ? t.sig : "";
      if (sig === last) return;
      last = sig;
      weeksP.sec.hidden = playersP.sec.hidden = !t;
      if (!t) return;
      var r = impact(ctx, t);
      if (r.error) {
        weeksP.body.replaceChildren(el("p", {class: "muted bw-fine", text: r.error}));
        playersP.sec.hidden = true;
        return;
      }
      var myName = r.data.sides[0].name;
      renderWeeks(weeksP.body, r.data, t);
      renderPlayers(playersP.body, r.data, myName);
    }
    // The live page redraws these on every pick, partner change and mode switch (build-trade.js render()).
    var queued = false;
    var later = function () { if (queued) return; queued = true; setTimeout(function () { queued = false; update(); }, 0); }; // not rAF: that waits while the tab is hidden
    var mo = new MutationObserver(later);
    ["give-names", "get-names", "lineup-body", "partner"].forEach(function (id) { var n = document.getElementById(id); if (n) mo.observe(n, {childList: true, subtree: true, characterData: true}); });
    mo.observe(anchor, {attributes: true, attributeFilter: ["hidden"]});
    mo.observe(document.body, {attributes: true, attributeFilter: ["class"]});
    document.addEventListener("change", later);
    update();
  }
  function whenLive(fn) {
    var tries = 0;
    (function poll() {
      if (window.DDFBuild && document.body.classList.contains("build-live")) return fn();
      if (++tries < 300) setTimeout(poll, 100);
    })();
  }
  ST.ready.then(function (ctx) { if (ctx && ctx.summary) whenLive(function () { start(ctx); }); });
})();
