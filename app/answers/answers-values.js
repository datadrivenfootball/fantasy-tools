/* Answers Values page (JEG-1543): the DDF Value list for the reader's league, from the pre-built tables. */
(function () {
  "use strict";
  var A = window.DDF && window.DDF.answers;
  if (!A) return;
  var $ = function (id) { return document.getElementById(id); };
  var pos = "", query = "";
  var FIELDS = {scoring: "f-scoring", teams: "f-teams", QB: "f-qb", WR: "f-wr", FLEX: "f-flex", SUPERFLEX: "f-sf", BENCH: "f-bench"};

  function show(el, text) { el.textContent = text || ""; el.hidden = !text; }
  function fmt(v) { return (Math.round(v * 10) / 10).toFixed(1); }
  function syncFields() {
    var s = A.settings();
    Object.keys(FIELDS).forEach(function (k) {
      var el = $(FIELDS[k]), v = k === "scoring" ? s.scoring : k === "teams" ? s.teams : s.roster[k];
      var opt = Array.prototype.find.call(el.options, function (o) { return o.value === String(v); });
      el.value = opt ? opt.value : el.options[0].value;
    });
  }

  function render() {
    var s = A.settings();
    $("ctx-league").textContent = A.label(s);
    var wk = A.week();
    $("ctx-week").textContent = wk ? "Week " + wk : "";
    var why = A.offGrid();
    var custom = why.some(function (w) { return /season weeks|advanced|position shares/.test(w); });
    show($("n-offgrid"), why.length ? "Values for these settings (" + why.join(", ") + ") are not shown here yet." +
      (custom ? "" : " Try the closest settings above.") : "");
    show($("n-error"), A.error() ? "The values did not load. Reload the page to try again." : "");
    $("n-basis").hidden = !A.basisIgnored();
    var ov = A.overrideCount();
    show($("n-ov"), ov ? "Your " + ov + (ov === 1 ? " override is" : " overrides are") + " applied (marked Your value)." : "");
    var card = $("list-card");
    if (!A.cell() || A.error()) { card.hidden = true; return; }
    card.hidden = false;
    var q = query.trim().toLowerCase();
    var all = A.players().filter(function (p) { return (!pos || p.pos === pos) && (!q || p.n.toLowerCase().indexOf(q) >= 0); });
    var shown = q ? all : all.filter(function (p) { return p.ddf > 0; });
    var body = $("rows");
    body.textContent = "";
    var frag = document.createDocumentFragment();
    shown.forEach(function (p, i) {
      var tr = document.createElement("tr");
      var cells = [String(i + 1), p.n, p.pos, p.team || "FA", fmt(p.ddf)];
      cells.forEach(function (text, c) {
        var td = document.createElement(c === 1 ? "th" : "td");
        if (c === 1) td.scope = "row";
        if (c === 0 || c === 4) td.className = "num";
        if (c === 3) td.className = "team";
        td.textContent = text;
        if (c === 1 && p.ov) { var t = document.createElement("span"); t.className = "tag yours"; t.textContent = "Your value"; td.appendChild(t); }
        if (c === 1 && p.low) { var u = document.createElement("span"); u.className = "tag unsure"; u.textContent = "Less certain"; td.appendChild(u); }
        tr.appendChild(td);
      });
      frag.appendChild(tr);
    });
    body.appendChild(frag);
    var zero = all.length - shown.length;
    $("more").textContent = shown.length ? (zero > 0 ? zero + " more players are priced at 0 here. Search finds them." : "")
      : "No player matches.";
  }

  document.getElementById("pos").addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-pos]");
    if (!b) return;
    pos = b.getAttribute("data-pos");
    Array.prototype.forEach.call(this.querySelectorAll("button"), function (x) { x.setAttribute("aria-pressed", String(x === b)); });
    render();
  });
  $("q").addEventListener("input", function () { query = this.value; render(); });
  Object.keys(FIELDS).forEach(function (k) {
    $(FIELDS[k]).addEventListener("change", function () {
      var partial = {roster: {}};
      Object.keys(FIELDS).forEach(function (key) {
        var v = $(FIELDS[key]).value;
        if (key === "scoring") partial.scoring = v;
        else if (key === "teams") partial.teams = Number(v);
        else partial.roster[key] = Number(v);
      });
      A.useVisit(partial);
    });
  });
  A.on(render);
  A.ready.then(function () { syncFields(); render(); });
})();
