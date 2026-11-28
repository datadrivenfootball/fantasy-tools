/* DDF staging: W-L, Playoffs %, Title % and FAAB left in Team › "How the league compares" (JEG-1736).
 * The live page's own script draws that table and redraws it when a team is selected or a column is sorted, so the
 * columns are added after each draw (a MutationObserver on the section; adding is idempotent). Rows are matched to the
 * stored teams by team name (the bridge's matched record), using the row's own team index only to split a shared name.
 * Odds are DDFWeekly.plan(...).standings; FAAB is summary.teams[].faab_remaining. Missing is "—" with its reason,
 * never 0. No posture labels (Jeremy, 2026-11-27: they wait for the JEG-1737 spec). Text is written with textContent.
 * Loaded by league-bridge.js (data-add) once the live page has its league. */
(function () {
  "use strict";
  var S = window.DDFStaging;
  if (!S) return;
  var isNum = function (x) { return typeof x === "number" && isFinite(x); };
  function summaryOf() { var S = window.DDFStaging; return (S && S.summary) || {}; }
  function platformName() { var p = String(summaryOf().platform || ""); return {yahoo: "Yahoo", espn: "ESPN", sleeper: "Sleeper"}[p] || "the league's platform"; }
  function noFaab() { var st = summaryOf().settings || {}; return st.waiver_type && st.waiver_type !== "faab"; }
  function el(tag, attrs) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] == null) return;
      if (k === "text") n.textContent = attrs[k]; else if (k === "class") n.className = attrs[k]; else n.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) { var c = arguments[i]; if (c != null && c !== false) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    return n;
  }
  function na(reason) { return el("span", {class: "tl-na", title: reason, "aria-label": "Not available. " + reason, text: "—"}); }
  function pct(p, reason) {
    if (!isNum(p)) return na(reason);
    var v = Math.round(p * 100);
    return v === 0 && p > 0 ? "<1%" : v === 100 && p < 1 ? ">99%" : v + "%";
  }
  var norm = function (s) { return String(s || "").replace(/\s+/g, " ").trim().toLowerCase(); };

  var data = null; /* {byName: {name: [team]}, byIndex: [team], fine: string} */
  var COLS = [
    {key: "wl", head: "W-L", info: "Win-loss record, as the league's platform had it when the league data was pulled."},
    {key: "playoffs", head: "PLAYOFFS", info: "Share of simulated seasons in which this team makes the playoffs."},
    {key: "title", head: "TITLE", info: "Share of simulated seasons in which this team wins the championship. Shown only when the full bracket can be played out."},
    {key: "faab", head: "FAAB", info: "Waiver budget left, as the league's platform had it when the league data was pulled."}
  ];

  function build(d) {
    var plan = null, planError = null;
    if (!d.weekly) planError = "Weekly projections could not be read" + (S.weeklyError ? ": " + S.weeklyError : "");
    else if (!window.DDFWeekly || typeof window.DDFWeekly.plan !== "function") planError = "The weekly planner did not load";
    else { try { plan = window.DDFWeekly.plan(d.summary, d.weekly, {myTeamKey: d.league.my_team_key}); } catch (e) { planError = e.message || String(e); } }
    var st = {};
    ((plan && plan.standings) || []).forEach(function (s) { st[s.team_key] = s; });
    var teams = (d.summary.teams || []).map(function (t) {
      var s = st[t.team_key] || null, own = t.standings || {};
      return {name: t.name, wins: s ? s.wins : own.wins, losses: s ? s.losses : own.losses, ties: s ? s.ties : own.ties,
        playoff_p: s ? s.playoff_p : null, title_p: s ? s.title_p : null, faab: t.faab_remaining, odds: !!s};
    });
    var byName = {};
    teams.forEach(function (t) { (byName[norm(t.name)] = byName[norm(t.name)] || []).push(t); });
    var runs = plan && plan.sim && isNum(plan.sim.runs) ? plan.sim.runs.toLocaleString("en-US") : null;
    var sb = d.weekly && d.weekly.scoring_basis;
    var fine = plan
      ? "Playoffs and Title are each team's chance: " + (runs || "many") + " simulated seasons, each game from weekly player projections" +
        (sb && sb.rescored === false ? " in each source's default scoring (your league's settings are not in the data)" : " rescored with your league's scoring settings") +
        "; games independent, tiebreak points for. Title odds need the full bracket. DDF Value is not used."
      : "Playoffs and Title odds are not available: " + planError + ".";
    fine += " W-L and FAAB (waiver budget left) are as " + platformName() + " had them when the league data was pulled. A dash (—) means the number is missing, not zero.";
    return {byName: byName, byIndex: teams, fine: fine, planError: planError, noTitle: !!plan && teams.every(function (t) { return !isNum(t.title_p); })};
  }

  function teamOf(tr) {
    var first = tr.cells[0];
    if (!first) return null;
    var name = "";
    Array.prototype.forEach.call(first.childNodes, function (n) { if (n.nodeType === 3) name += n.textContent; }); /* the badge is a child element */
    var hits = data.byName[norm(name)] || [];
    if (hits.length === 1) return hits[0];
    var at = data.byIndex[Number(tr.dataset.team)];
    return hits.length > 1 && at && hits.indexOf(at) >= 0 ? at : null;
  }
  function cells(t) {
    var noOdds = data.planError || "This team is not in the simulation";
    function td(key, child) { return el("td", {class: "tl-col tl-" + key, "data-tl": key}, child); }
    if (!t) { var why = "This row did not match a team in the stored league"; return COLS.map(function (c) { return td(c.key, na(why)); }); }
    return [
      td("wl", isNum(t.wins) && isNum(t.losses) ? t.wins + "-" + t.losses + (t.ties ? "-" + t.ties : "") : na("Record not read from the league")),
      td("playoffs", pct(t.playoff_p, noOdds)),
      td("title", pct(t.title_p, t.odds ? "Title odds need the full bracket, and the playoff weeks are not all in the data" : noOdds)),
      td("faab", isNum(t.faab) ? "$" + t.faab : noFaab() ? na("This league has no FAAB") : na("FAAB not read from the league"))
    ];
  }

  function section() {
    var h = document.getElementById("cmp-title");
    return h ? h.closest("section") : null;
  }
  function apply() {
    var sec = section();
    if (!sec || !data) return;
    var table = sec.querySelector("table"), head = table && table.tHead && table.tHead.rows[0];
    if (!head) return;
    sec.classList.add("tl-on");
    if (!head.querySelector("[data-tl]")) {
      COLS.forEach(function (c) {
        /* no ⓘ per column: the line under the table says what each one is, and the table has no width to spare */
        head.appendChild(el("th", {scope: "col", class: "tl-col", "data-tl": c.key, title: c.info}, el("span", {class: "tl-head", text: c.head})));
      });
    }
    Array.prototype.forEach.call(table.tBodies, function (body) {
      Array.prototype.forEach.call(body.rows, function (tr) {
        if (tr.querySelector("[data-tl]")) return;
        cells(teamOf(tr)).forEach(function (c) { tr.appendChild(c); });
      });
    });
    if (!sec.querySelector(".tl-fine")) sec.appendChild(el("p", {class: "tl-fine", text: data.fine}));
  }

  S.ready.then(function (d) {
    data = build(d);
    apply();
    /* The live script redraws the rows (select, sort) and may redraw the table; re-add after each. */
    var root = section() || document.getElementById("league") || document.body, queued = false;
    new MutationObserver(function () {
      if (queued) return;
      queued = true;
      Promise.resolve().then(function () { queued = false; apply(); });
    }).observe(root, {childList: true, subtree: true});
  });
})();
