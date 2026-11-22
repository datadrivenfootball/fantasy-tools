/* Injury flag on a player in a trade (Jeremy, 2026-11-22: "We should denote injured players on the trade
 * recommendations, as our trade suggestion may not work perfectly. It is a flag, not a stopper.").
 *
 * Display only. Nothing here changes a label (Natural / Partner neutral / Force / Not judged), a rule, a count, an
 * order or a value: callers add the chip, the card line and the Why line next to what they already draw.
 *
 * Status: the daily Sleeper copy (window.TradeValueStatus, v2/player-status.js) under the Waivers rule
 * (DDFStatusRule.statusFreshness / statusOf, app/v2/player-status-rule.js, which the Waivers tab uses too): shown only when dated and at most 6 days old, and
 * only when the Sleeper id, NFL team and position all match the row. No status means no chip, never "healthy".
 * Body part: the same copy's injury_body_part ("Hamstring"), when present.
 *
 * API window.DDFInjury (node can require this file: tests/test_injury_flag.py)
 *   severity(status)        -> {status, label, level, rank} or null. level "out" | "doubtful" | "questionable".
 *   freshness()             -> the Waivers freshness of the loaded copy (browser), or null
 *   flagOf(row, freshness?) -> {key, name, status, label, level, body, aria, title} or null
 *   flagsOf(rows, fr?)      -> the flagged rows' flags, in the input order, one per player
 *   chip(flag)              -> '<span class="inj-chip" ...>Out</span>' or ""
 *   summary(flags)          -> "Injury flag on 1 player" or ""
 *   whyLine(flag)           -> "Injury flag: X is Out (hamstring). A flag, not a stopper: the trade may not work as planned."
 *   note(rows, fr?)         -> the card line (summary with the flag-not-stopper tooltip) as HTML, or ""
 *   whyHtml(rows, fr?)      -> the Why panel's lines as HTML, or ""
 */
(function (root) {
  "use strict";
  var LEVELS = {out: 0, doubtful: 1, questionable: 2};
  // Sleeper's injury_status values (and the one-letter tags Yahoo shows) -> the chip.
  var SEVERITY = {
    Out: {label: "Out", level: "out", phrase: "Out"},
    IR: {label: "IR", level: "out", phrase: "on IR"},
    PUP: {label: "PUP", level: "out", phrase: "on PUP"},
    Sus: {label: "Suspended", level: "out", phrase: "Suspended"},
    Doubtful: {label: "Doubtful", level: "doubtful", phrase: "Doubtful"},
    Questionable: {label: "Questionable", level: "questionable", phrase: "Questionable"}
  };
  var ALIASES = {OUT: "Out", O: "Out", IR: "IR", "INJURED RESERVE": "IR", PUP: "PUP", SUS: "Sus", SUSP: "Sus",
    SUSPENDED: "Sus", DOUBTFUL: "Doubtful", D: "Doubtful", QUESTIONABLE: "Questionable", Q: "Questionable"};
  var NOTE_TITLE = "A flag, not a stopper: the injury status does not change the fit label, the order or any value.";
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };

  function severity(status) {
    var name = typeof status === "string" ? ALIASES[status.trim().toUpperCase()] : null;
    var s = name ? SEVERITY[name] : null;
    return s ? {status: name, label: s.label, level: s.level, rank: LEVELS[s.level], phrase: s.phrase} : null;
  }

  function waivers() { return root.DDFStatusRule || root.TradeValueWaivers || null; }
  function freshness() {
    var W = waivers();
    return W && W.statusFreshness ? W.statusFreshness(root.TradeValueStatus || null, Date.now()) : null;
  }
  function bodyOf(row, fr) {
    var p = fr && fr.bySleeperId && row ? fr.bySleeperId[String(row.sleeper_id)] : null;
    var text = p && typeof p.injury_body_part === "string" ? p.injury_body_part.replace(/\s+/g, " ").trim() : "";
    return text ? text.slice(0, 40).toLowerCase() : null;
  }
  function flagOf(row, fr) {
    var W = waivers();
    if (!row || !W || !W.statusOf) return null;
    if (fr === undefined) fr = freshness();
    var s = severity(W.statusOf(row, fr));
    if (!s) return null;
    var body = bodyOf(row, fr);
    var aria = "Injury: " + s.label + (body ? ", " + body : "");
    return {key: row.player_key === undefined ? null : String(row.player_key), name: row.name, status: s.status,
      label: s.label, level: s.level, rank: s.rank, phrase: s.phrase, body: body, aria: aria,
      title: aria + (fr && fr.label ? " (" + fr.label + ")" : "") + ". " + NOTE_TITLE};
  }
  function flagsOf(rows, fr) {
    if (fr === undefined) fr = freshness();
    var seen = {};
    return (rows || []).map(function (r) { return flagOf(r, fr); }).filter(function (f) {
      var id = f && (f.key || f.name);
      if (!f || seen[id]) return false;
      seen[id] = true;
      return true;
    });
  }
  function chip(flag) {
    if (!flag) return "";
    return '<span class="inj-chip" data-injury-chip data-level="' + esc(flag.level) + '" data-status="' + esc(flag.status)
      + '" role="img" aria-label="' + esc(flag.aria) + '" title="' + esc(flag.title) + '">' + esc(flag.label) + "</span>";
  }
  function summary(flags) {
    var n = (flags || []).length;
    return n ? "Injury flag on " + n + (n === 1 ? " player" : " players") : "";
  }
  function whyLine(flag) {
    return flag ? "Injury flag: " + flag.name + " is " + flag.phrase + (flag.body ? " (" + flag.body + ")" : "")
      + ". A flag, not a stopper: the trade may not work as planned." : "";
  }
  function note(rows, fr) {
    var flags = flagsOf(rows, fr);
    return flags.length ? '<p class="muted pk-note inj-note" data-injury-summary="' + flags.length + '" title="' + esc(NOTE_TITLE) + '">'
      + esc(summary(flags)) + "</p>" : "";
  }
  function whyHtml(rows, fr) {
    var flags = flagsOf(rows, fr);
    return flags.length ? '<div class="inj-why" data-injury-why>' + flags.map(function (f) { return "<p>" + esc(whyLine(f)) + "</p>"; }).join("")
      + "</div>" : "";
  }

  var CSS = ".inj-chip{display:inline-block;margin-left:6px;padding:0 6px;border:1px solid;border-radius:999px;font-family:inherit;"
    + "font-size:11px;font-weight:700;line-height:17px;letter-spacing:0;text-transform:none;white-space:nowrap;vertical-align:1px}"
    + ".inj-chip[data-level=out]{color:#8a2d1b;background:#fdf1ed;border-color:#e2b6a9}"
    + ".inj-chip[data-level=doubtful]{color:#7a4500;background:#fff5e3;border-color:#e6c48a}"
    + ".inj-chip[data-level=questionable]{color:#5a5200;background:#fbf9e6;border-color:#d6cd98}"
    + ".inj-note{color:#6b4a16}.inj-why{margin:8px 0;padding:8px 10px;border-left:3px solid #e6c48a;background:#fffaf0;font-size:13px;line-height:1.4}"
    + ".inj-why p{margin:0}.inj-why p+p{margin-top:4px}.inj-name{overflow-wrap:anywhere}";
  function injectCss() {
    if (!root.document || !root.document.head || root.document.getElementById("inj-flag-css")) return;
    var st = root.document.createElement("style");
    st.id = "inj-flag-css";
    st.textContent = CSS;
    root.document.head.appendChild(st);
  }

  var api = {SEVERITY: SEVERITY, NOTE_TITLE: NOTE_TITLE, severity: severity, freshness: freshness, flagOf: flagOf, flagsOf: flagsOf,
    chip: chip, summary: summary, whyLine: whyLine, note: note, whyHtml: whyHtml, injectCss: injectCss};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  injectCss();
  root.DDFInjury = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
