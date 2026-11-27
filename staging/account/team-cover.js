/* DDF staging: the Cover panel on Team (JEG-1736). Renders DDFWeekly.cover(summary, weekly, my_team_key) as
 * documented in docs/signed-in-features.md, after "Strengths, needs and what to do next". Weekly projections only:
 * no DDF Value here. A missing number is "—" with its reason, never 0; a bye reads BYE. Text is written with
 * textContent. Loaded by league-bridge.js (data-add) once the live page has its league. */
(function () {
  "use strict";
  var S = window.DDFStaging;
  if (!S) return;
  function el(tag, attrs) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] == null) return;
      if (k === "text") n.textContent = attrs[k]; else if (k === "class") n.className = attrs[k]; else n.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) { var c = arguments[i]; if (c != null && c !== false) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    return n;
  }
  var isNum = function (x) { return typeof x === "number" && isFinite(x); };
  function na(reason) { return el("span", {class: "cv-na", title: reason, "aria-label": "Not available. " + reason, text: "—"}); }
  function cost(x) { return x === 0 ? "0.0" : "−" + Math.abs(x).toFixed(1); } /* a cost is points lost */
  var last = function (name) { var p = String(name || "").split(" "); return p.length > 1 ? p.slice(1).join(" ") : p[0]; };
  var KIND = {hole: ["Hole", "weak"], thin: ["Thin", "average"], ok: ["Covered", "strong"]};

  function weekCell(c, w) {
    var td = el("td", {class: "cv-wk", "data-week": "Wk " + w});
    if (!c) { td.appendChild(na("No projection for week " + w)); return td; }
    if (c.bye) { td.appendChild(el("span", {class: "cv-bye", text: "BYE"})); return td; }
    if (!c.starts) { td.appendChild(el("span", {class: "cv-out", text: "Bench", title: "Not in your best lineup this week, so losing him costs nothing"})); return td; }
    td.appendChild(el("b", {class: "cv-cost" + (isNum(c.cost) && c.cost >= 5 ? " big" : "")}, isNum(c.cost) ? cost(c.cost) : na(isNum(c.points) ? "No lineup total this week" : "No projection for him this week")));
    td.appendChild(el("small", {text: c.cover ? last(c.cover.name) + (isNum(c.cover.points) ? " " + c.cover.points.toFixed(1) : "") : c.empty ? "Slot empty" : "No one in"}));
    return td;
  }
  function starterRows(cover) {
    var names = {};
    cover.starters.forEach(function (s) { names[s.player_id] = s.name; });
    return cover.starters.map(function (s) {
      var k = KIND[s.kind] || KIND.ok;
      var who = el("th", {scope: "row", class: "cv-who"}, el("span", {class: "posname"}, s.name || "Unknown player", s.status ? el("span", {class: "cv-st", text: s.status}) : null),
        el("span", {class: "players", text: s.pos || ""}));
      var state = el("td", {class: "cv-state"}, el("b", {class: "tier " + k[1], text: k[0]}));
      var shared = (s.shared_with || []).map(function (id) { return names[id]; }).filter(Boolean);
      if (shared.length) state.appendChild(el("small", {title: shared.join(", "), text: "Same backup as " + shared.slice(0, 2).map(last).join(", ") + (shared.length > 2 ? " and " + (shared.length - 2) + " more" : "")}));
      var tr = el("tr", {class: "cv-" + (s.kind || "ok")}, who, state);
      cover.weeks.forEach(function (w) { tr.appendChild(weekCell((s.weeks || {})[w], w)); });
      tr.appendChild(el("td", {class: "cv-total num", "data-week": "Weeks left"}, isNum(s.total_cost) ? cost(s.total_cost) : na("A week has no projection, so there is no total")));
      return tr;
    });
  }
  function kdefRows(cover) {
    return (cover.kdef || []).map(function (k) {
      var label = k.pos === "DEF" ? "Defense" : "Kicker";
      var who = el("th", {scope: "row", class: "cv-who"}, el("span", {class: "posname", text: k.starter ? k.starter.name : "No " + label.toLowerCase()}), el("span", {class: "players", text: k.pos}));
      var state = el("td", {class: "cv-state"}, el("b", {class: "tier " + (k.backup ? "strong" : k.starter ? "average" : "weak"), text: k.backup ? "Backup" : k.starter ? "No backup" : "Hole"}),
        el("small", {text: k.backup ? k.backup.name : k.best_add ? "Best add: " + k.best_add.name : "No add found in the league's free agents"}));
      var tr = el("tr", {class: "cv-kdef"}, who, state), sum = 0, ok = !!k.starter;
      cover.weeks.forEach(function (w) {
        var sw = (k.starter_weeks || {})[w], c = (k.cost || {})[w], td = el("td", {class: "cv-wk", "data-week": "Wk " + w});
        if (sw && sw.bye) td.appendChild(el("span", {class: "cv-bye", text: "BYE"}));
        else td.appendChild(el("b", {class: "cv-cost"}, isNum(c) ? cost(c) : na(k.starter ? "No projection for week " + w : "No " + label.toLowerCase() + " on your roster")));
        var add = k.best_add && k.best_add.weeks ? k.best_add.weeks[w] : null;
        if (!k.backup && k.best_add) td.appendChild(el("small", {}, last(k.best_add.name) + " ", isNum(add) ? add.toFixed(1) : na("No projection for week " + w)));
        if (isNum(c)) sum += c; else if (!(sw && sw.bye)) ok = false;
        tr.appendChild(td);
      });
      tr.appendChild(el("td", {class: "cv-total num", "data-week": "Weeks left"}, ok ? cost(sum) : na("A week has no projection, so there is no total")));
      return tr;
    });
  }

  function render(cover, sample) {
    var sec = el("section", {class: "card cover", id: "team-cover", "aria-labelledby": "cover-title"});
    sec.appendChild(el("h2", {id: "cover-title"}, "Cover: if a starter goes down",
      el("details", {class: "info"}, el("summary", {"aria-label": "How cover is worked out", text: "ⓘ"}),
        el("span", {text: "For each week left we set your best lineup on weekly projections, then set it again without that player. The cost is the points you lose, and the name under it is who steps in. Hole: a slot goes empty, or you lose half his points or more. Thin: you lose a quarter or more."}))));
    sec.appendChild(el("p", {class: "cv-intro", text: "What losing each starter costs your lineup in the weeks left, and who steps in. Holes first." + (sample ? " Sample numbers." : "")}));
    /* Jeremy, 2026-11-27: every weekly number says its source and whether it is in the league's own scoring */
    var sb = (S && S.weekly && S.weekly.scoring_basis) || null;
    if (sb && sb.text) sec.appendChild(el("p", {class: "cv-intro cv-basis", text: "Numbers: ESPN's weekly projected stats (Sleeper's where ESPN has none; K and DEF from ESPN). " + sb.text}));
    if (!cover.starters.length && !(cover.kdef || []).length) { sec.appendChild(el("p", {class: "empty", text: "No starters to show for the weeks left."})); return sec; }
    var counts = {hole: 0, thin: 0};
    cover.starters.forEach(function (s) { if (counts[s.kind] !== undefined) counts[s.kind]++; });
    sec.appendChild(el("p", {class: "team-context cv-sum", text: (counts.hole ? counts.hole + (counts.hole === 1 ? " hole" : " holes") : "No holes") + ", " + (counts.thin ? counts.thin + " thin" : "none thin") + ", over weeks " + cover.weeks[0] + " to " + cover.weeks[cover.weeks.length - 1] + "."}));
    var head = el("tr", {}, el("th", {scope: "col", text: "STARTER"}), el("th", {scope: "col", text: "COVER"}));
    cover.weeks.forEach(function (w) { head.appendChild(el("th", {scope: "col", class: "cv-wk", text: "WK " + w})); });
    head.appendChild(el("th", {scope: "col", class: "num", text: "WEEKS LEFT"}));
    var body = el("tbody");
    starterRows(cover).forEach(function (r) { body.appendChild(r); });
    var kd = kdefRows(cover);
    if (kd.length) { body.appendChild(el("tr", {class: "cv-sep"}, el("th", {colspan: String(cover.weeks.length + 3), scope: "rowgroup", text: "Kicker and defense: starter over backup"}))); kd.forEach(function (r) { body.appendChild(r); }); }
    sec.appendChild(el("div", {class: "table-wrap"}, el("table", {class: "cv-table"}, el("caption", {class: "cv-sr", text: "Points your best lineup loses each week without each starter, and who steps in"}), el("thead", {}, head), body)));
    var notes = el("ul", {class: "cv-notes"});
    (cover.notes || []).forEach(function (n) { notes.appendChild(el("li", {text: n})); });
    notes.appendChild(el("li", {text: "A dash (—) means the number is missing, not zero."}));
    sec.appendChild(notes);
    return sec;
  }
  function place(node) {
    var old = document.getElementById("team-cover"), after = document.getElementById("team-assets");
    if (old) old.remove();
    if (after) after.insertAdjacentElement("afterend", node);
  }
  function message(text) { place(el("section", {class: "card cover", id: "team-cover"}, el("h2", {text: "Cover: if a starter goes down"}), el("p", {class: "muted", text: text}))); }

  S.ready.then(function (d) {
    if (S.mock) {
      var s = document.createElement("script");
      s.src = S.url("team-cover-mock.js");
      s.onload = function () { place(render(window.DDFStagingMockCover(d.summary), true)); };
      s.onerror = function () { message("Sample cover data did not load."); };
      document.head.appendChild(s);
      return;
    }
    if (!d.weekly) { message("Weekly projections could not be read" + (S.weeklyError ? ": " + S.weeklyError : ".")); return; }
    if (!window.DDFWeekly || typeof window.DDFWeekly.cover !== "function") { message("The weekly planner did not load. Reload the page."); return; }
    try { place(render(window.DDFWeekly.cover(d.summary, d.weekly, d.league.my_team_key), false)); }
    catch (e) { message(e.message || String(e)); }
  });
})();
