/* One starting lineup before and after a trade, drawn the same way on every page (Jeremy, 2026-11-22: Build a Trade
 * lineup card, layout A "Changes first"). No value math: the input is DDFWhy.lineupTable(teamFitSide, shape, arriving,
 * {natural, who}) (ddf-why.js), which reads tradeFit / teamFit's own lineupValue calls.
 *
 * API: window.DDFLineup
 *   html(lineup, opts) -> one side, in one of three sizes:
 *     size "line"    Find offer card: starters before -> after, change chip, "In: .. Out: ..", one flag chip.
 *                    opts {who, title, basis}; keeps the card's data-lineup / data-before / data-after.
 *     size "changes" Build a Trade card: changed slots open (who starts now, tag, value, slot change, who loses it),
 *                    unchanged starters (and K / DEF, not valued) folded to one line, the bench folded to one line,
 *                    flag chips. opts {who, title}.
 *     size "full"    every slot, Before | After (the Why panel's table). opts {title, basis}.
 *   summary(lineup, opts) -> one totals line "Your starters on DDF Value 209.3 -> 220.1 +10.8"; opts {who, title, basis,
 *     note} (note: a line in place of the numbers when that side cannot be shown).
 *   card(sides, opts) -> the Build a Trade card body: both totals first, then each side at "changes" size.
 *     sides: [{lineup|null, who, title, sumTitle, basis, note}], opts {foot}.
 */
(function () {
  "use strict";
  var FLOOR = 0.05;
  var finite = function (v) { return typeof v === "number" && isFinite(v); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var one = function (n) { return finite(n) ? n.toFixed(1) : "—"; };
  var shown = function (n) { return !finite(n) ? "—" : Math.abs(n) < FLOOR ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1); };
  var dirOf = function (n) { return !finite(n) || Math.abs(n) < FLOOR ? "flat" : n > 0 ? "up" : "down"; };
  var arrow = function (a, b, cls) {
    return '<span class="' + cls + '">' + one(a) + '</span> <span aria-hidden="true">&rarr;</span><span class="lu-sr"> to </span> <span class="' + cls + '">' + one(b) + "</span>";
  };
  var valued = function (rows) { return rows.filter(function (r) { return !r.unvalued; }); };

  // ---------- "line": the Find offer card ----------
  function line(t, o) {
    var nm = function (x) { return x.name + (x.slot ? " (" + x.slot + ")" : ""); };
    var ins = t.moves["in"], outs = t.moves.out;
    var moves = ins.length || outs.length
      ? (ins.length ? "In: " + ins.map(nm).join(", ") + "." : "") + (outs.length ? (ins.length ? " " : "") + "Out: " + outs.map(nm).join(", ") + "." : "")
      : "No lineup change.";
    var flag = (t.flags || []).filter(function (f) { return !f.ok; })[0];
    return '<div class="lm" data-lineup="' + esc(o.who) + '" data-before="' + t.before.toFixed(1) + '" data-after="' + t.after.toFixed(1) + '">'
      + '<div class="lm-top"><span class="lm-h">' + esc(o.title) + " <i>" + esc(o.basis) + '</i></span><span class="lm-d" data-dir="' + dirOf(t.delta) + '">' + shown(t.delta) + "</span></div>"
      + '<div class="lm-n">' + t.before.toFixed(1) + ' <span aria-hidden="true">&rarr;</span><span class="lm-sr"> to </span> ' + t.after.toFixed(1) + "</div>"
      + '<p class="lm-mv">' + esc(moves) + "</p>"
      + (flag ? '<p class="lu-flags"><span class="lu-flag" data-flag="' + esc(flag.kind) + '">' + esc(flag.text) + "</span></p>" : "")
      + "</div>";
  }

  // ---------- "full": the Why panel's table ----------
  function full(t, o) {
    var c = function (x, kdef) {
      if (!x) return kdef ? '<td class="why-pl"><span class="why-nm">—</span><span class="why-v">not valued</span></td>' : '<td class="why-pl why-empty">Empty</td>';
      return '<td class="why-pl"><span class="why-nm">' + esc(x.name) + '</span><span class="why-v">' + (kdef ? "not valued" : one(x.value)) + "</span>"
        + (x.tag ? '<span class="why-mv" data-tag="' + esc(x.tag) + '">' + esc(x.tag) + "</span>" : "") + "</td>";
    };
    var tr = function (r) {
      var cls = [r.changed ? "why-chg" : "", r.unvalued ? "why-kdef" : ""].filter(Boolean).join(" ");
      return "<tr" + (cls ? ' class="' + cls + '"' : "") + (r.unvalued ? " data-unvalued" : "") + '><th scope="row">' + esc(r.slot) + "</th>" + c(r.before, r.unvalued) + c(r.after, r.unvalued) + "</tr>";
    };
    return '<div class="why-lu"><p class="why-lu-h"><b>' + esc(o.title) + "</b> <small>" + esc(o.basis) + "</small></p>"
      + '<table class="why-lt"><thead><tr><th scope="col"><span class="why-sr">Slot</span></th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>'
      + t.rows.concat(t.extra || []).map(tr).join("")
      + '</tbody></table><p class="why-tot" data-starters-before="' + one(t.before) + '" data-starters-after="' + one(t.after) + '"><span>Starters</span> <span class="why-n">' + one(t.before)
      + '</span> to <span class="why-n">' + one(t.after) + '</span> <span class="why-d" data-dir="' + dirOf(t.delta) + '">' + shown(t.delta) + "</span></p></div>";
  }

  // ---------- "changes": the Build a Trade card ----------
  var valueOf = function (x) { return x && finite(x.value) ? x.value : 0; };   // an empty slot adds nothing to the starters
  function changedRow(r) {
    var a = r.after, b = r.before, d = valueOf(a) - valueOf(b);
    var now = a
      ? '<b class="lu-nm">' + esc(a.name) + '</b> <span class="lu-v">' + one(a.value) + "</span>" + (a.tag ? ' <span class="lu-tag" data-tag="' + esc(a.tag) + '">' + esc(a.tag) + "</span>" : "")
      : '<b class="lu-nm lu-empty">Empty</b>';
    var was = b ? 'for <s>' + esc(b.name) + " " + one(b.value) + "</s>" : "an empty slot before";
    return '<div class="lu-row lu-chg" data-slot="' + esc(r.slot) + '" data-changed><span class="lu-slot">' + esc(r.slot) + '</span><span class="lu-now">' + now + "</span>"
      + '<span class="lu-d" data-dir="' + dirOf(d) + '">' + shown(d) + '</span><span class="lu-was">' + was + "</span></div>";
  }
  function sameRow(r) {
    var a = r.after || r.before;
    // K / DEF are never valued: the row names who is rostered there (a dash when the league did not list one).
    var who = r.unvalued ? '<span class="lu-nm">' + esc(a ? a.name : "—") + '</span> <span class="lu-v">not valued</span>'
        + (r.changed && r.before && r.after ? ' <span class="lu-was">for ' + esc(r.before.name) + "</span>" : "")
      : a ? '<span class="lu-nm">' + esc(a.name) + '</span> <span class="lu-v">' + one(a.value) + "</span>" : '<span class="lu-nm lu-empty">Empty</span>';
    return '<div class="lu-row" data-slot="' + esc(r.slot) + '"' + (r.unvalued ? " data-unvalued" : "") + '><span class="lu-slot">' + esc(r.slot) + '</span><span class="lu-now">' + who + "</span></div>";
  }
  // "5 starters unchanged, plus K and DEF" (K and DEF are never valued, so they never count as starters here).
  function sameWords(n, extra) {
    var kd = extra.map(function (r) { return r.slot; }).filter(function (x, i, a) { return a.indexOf(x) === i; });
    var head = n ? n + (n === 1 ? " starter" : " starters") + " unchanged" : "";
    return head && kd.length ? head + ", plus " + kd.join(" and ") : head || kd.join(" and ");
  }
  function benchWords(b) {
    var parts = b.left.map(function (x) { return x.name + (x.how === "up" ? " up" : " traded"); })
      .concat(b.joined.map(function (x) { return x.name + (x.how === "down" ? " down" : x.how === "arrives" ? " arrives" : " joins"); }));
    return parts.length ? parts.join(", ") : "No change";
  }
  function flagsHtml(flags) {
    if (!flags || !flags.length) return "";
    return '<p class="lu-flags">' + flags.map(function (f) { return '<span class="lu-flag' + (f.ok ? " lu-ok" : "") + '" data-flag="' + esc(f.kind) + '">' + esc(f.text) + "</span>"; }).join("") + "</p>";
  }
  function changes(t, o) {
    var rows = valued(t.rows), ch = rows.filter(function (r) { return r.changed; });
    var same = rows.filter(function (r) { return !r.changed; }).concat(t.extra || []);
    var b = t.bench;
    var head = ch.length ? ch.length + " of " + rows.length + " slots change" : "No starting slot changes";
    return '<div class="lu-side" data-lineup-side="' + esc(o.who) + '"><p class="lu-head"><b>' + esc(o.title) + "</b><span>" + esc(head) + "</span></p>"
      + ch.map(changedRow).join("")
      + (same.length ? '<details class="lu-fold" data-fold="same"><summary><span>' + esc(sameWords(rows.length - ch.length, t.extra || [])) + "</span></summary>"
        + same.map(sameRow).join("") + "</details>" : "")
      + '<details class="lu-fold" data-fold="bench"><summary><span><b>Bench</b> · ' + esc(benchWords(b)) + '</span><span class="lu-n" data-bench-before="' + one(b.valueBefore) + '" data-bench-after="' + one(b.valueAfter) + '">'
      + arrow(b.valueBefore, b.valueAfter, "lu-bn") + "</span></summary>"
      + (b.after.length ? b.after.map(function (x) { return '<div class="lu-row"><span class="lu-slot">' + esc(x.pos) + '</span><span class="lu-now"><span class="lu-nm">' + esc(x.name) + '</span> <span class="lu-v">' + one(x.value) + "</span></span></div>"; }).join("")
        : '<p class="lu-none">No bench players after the trade.</p>')
      + "</details>"
      + flagsHtml(t.flags) + "</div>";
  }

  function summary(t, o) {
    var who = '<span class="lu-who">' + esc(o.title) + (o.basis ? "<small>on " + esc(o.basis) + "</small>" : "") + "</span>";
    if (!t) return '<div class="lu-sum" data-lineup-sum="' + esc(o.who) + '" data-missing>' + who + '<span class="lu-note">' + esc(o.note || "") + "</span></div>";
    return '<div class="lu-sum" data-lineup-sum="' + esc(o.who) + '" data-before="' + one(t.before) + '" data-after="' + one(t.after) + '" data-delta="' + shown(t.delta) + '">' + who
      + '<span class="lu-n">' + arrow(t.before, t.after, "lu-tn") + '</span><span class="lu-d" data-dir="' + dirOf(t.delta) + '">' + shown(t.delta) + "</span></div>";
  }
  function card(sides, opts) {
    opts = opts || {};
    injectCss();
    return '<div class="lu" data-lineup-card>'
      + '<div class="lu-sums">' + sides.map(function (s) { return summary(s.lineup, {who: s.who, title: s.sumTitle, basis: s.basis, note: s.note}); }).join("") + "</div>"
      + '<div class="lu-sides">' + sides.filter(function (s) { return s.lineup; }).map(function (s) { return changes(s.lineup, {who: s.who, title: s.title}); }).join("") + "</div>"
      + (opts.foot ? '<p class="lu-foot">' + esc(opts.foot) + "</p>" : "") + "</div>";
  }
  function html(t, opts) {
    opts = opts || {};
    if (!t) return "";
    injectCss();
    return opts.size === "line" ? line(t, opts) : opts.size === "full" ? full(t, opts) : changes(t, opts);
  }

  var CSS = ".lu{display:grid;gap:14px;min-width:0}.lu-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}"
    + ".lu-sums{display:grid;grid-template-columns:minmax(0,1fr);gap:8px}"
    + ".lu-sum{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:4px 10px;align-items:baseline;min-width:0}"
    + ".lu-who{font-weight:700;font-size:15px;line-height:1.25;min-width:0}.lu-who small{display:block;font-weight:500;font-size:12.5px;color:#5c6a76}"
    + ".lu-n{font-family:'IBM Plex Mono',monospace;font-size:14px;font-variant-numeric:tabular-nums;white-space:nowrap}"
    + ".lu-d{font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:13px;padding:1px 8px;border-radius:6px;background:#e9ecef;color:#39413b;white-space:nowrap;font-variant-numeric:tabular-nums;justify-self:end}"
    + ".lu-d[data-dir=up]{background:#e3f1ea;color:#176c4d}.lu-d[data-dir=down]{background:#f8e4e0;color:#8f2c20}"
    + ".lu-sum[data-missing]{grid-template-columns:minmax(0,1fr)}.lu-note{font-size:14px;color:#5c6a76}"
    + ".lu-sides{display:grid;grid-template-columns:minmax(0,1fr);gap:14px}"
    + ".lu-side{display:grid;gap:6px;align-content:start;min-width:0;padding-top:12px;border-top:1px solid #eef1ec}"
    + ".lu-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 10px;margin:0;font-size:14px}.lu-head span{color:#5c6a76;font-size:13px}"
    + ".lu-row{display:grid;grid-template-columns:3.2em minmax(0,1fr) auto;gap:2px 8px;align-items:start;padding:6px 8px;border-radius:8px;font-size:14px;line-height:1.3}"
    + ".lu-chg{background:#e3f1ea}.lu-slot{font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:11.5px;color:#5c6a76;padding-top:2px}.lu-chg .lu-d{background:#fff}"
    + ".lu-now{min-width:0;overflow-wrap:anywhere}.lu-nm{overflow-wrap:anywhere}.lu-v{font-family:'IBM Plex Mono',monospace;font-size:12.5px;color:#5c6a76;white-space:nowrap}"
    + ".lu-tag{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#176c4d;white-space:nowrap}"
    + ".lu-tag[data-tag=moves],.lu-tag[data-tag='from bench']{color:#7a4800}.lu-empty{color:#8f2c20}"
    + ".lu-was{grid-column:2/-1;font-size:13px;color:#5c6a76;overflow-wrap:anywhere}.lu-was s{text-decoration-thickness:1px}"
    + ".lu-fold>summary{display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:44px;padding:0 8px;cursor:pointer;list-style:none;font-size:14px;color:#176c4d;font-weight:600;border-radius:8px}"
    + ".lu-fold>summary::-webkit-details-marker{display:none}.lu-fold>summary>span:first-child{min-width:0}.lu-fold>summary>span:first-child::before{content:\"\\25B8\";display:inline-block;width:1.1em}"
    + ".lu-fold[open]>summary>span:first-child::before{content:\"\\25BE\"}.lu-fold>summary b{color:#12202c}.lu-fold>summary .lu-n{color:#39413b;font-size:13px}"
    + ".lu-fold>summary:focus-visible{outline:3px solid #176c4d;outline-offset:2px}.lu-none{margin:0;padding:4px 8px;font-size:13px;color:#5c6a76}"
    + ".lu-flags{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 0}.lu-flag{font-size:12.5px;font-weight:600;line-height:1.3;border-radius:99px;padding:3px 10px;background:#fff0e8;color:#a83e12}.lu-flag.lu-ok{background:#e3f1ea;color:#176c4d}"
    + ".lu-foot{margin:0;font-size:13px;color:#5c6a76}"
    + "@media(min-width:761px){.lu-sums,.lu-sides{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px 28px}}"
    // The Find card's chip sits under its In / Out line.
    + ".lm .lu-flags{margin:4px 0 0}";
  function injectCss() {
    if (typeof document === "undefined" || !document.head || document.getElementById("ddf-lineup-css")) return;
    var s = document.createElement("style");
    s.id = "ddf-lineup-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  injectCss();
  window.DDFLineup = {html: html, summary: summary, card: card};
})();
