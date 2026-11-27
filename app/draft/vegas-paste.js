// Vegas season player props from a pasted sportsbook page (JEG-1667).
// Jeremy, 2026-11-27: "I'll paste the lines." Pure, no network: the user
// selects all on a sportsbook's season player props page, copies and pastes;
// this reads the over/under lines for the seven markets the engine uses
// (DraftEngine.VEGAS_MARKETS) and fails closed on anything that looks like
// prop data but cannot be read, listing those lines.
//
// Layouts read (one or more per paste):
//   market header line ("Regular Season Passing Yards", "Receptions - 2026
//   Regular Season"), then per player: a name line, then "O 4100.5" /
//   "Over 4100.5" (odds on the same or the next line are ignored);
//   or "Josh Allen - Regular Season Passing Yards" followed by Over/Under;
//   or one line: "Josh Allen Over 3850.5 Passing Yards -110".
// Under lines are used only when a player has no over line in that market.
(function (root) {
  "use strict";

  // Market keywords -> engine market keys. Order matters: TDs before yards.
  var MARKETS = [
    { key: "season_pass_tds", re: /pass(ing)?\s*(td|tds|touchdowns?)/i },
    { key: "season_pass_yds", re: /pass(ing)?\s*(yds|yards?)/i },
    { key: "season_rush_tds", re: /rush(ing)?\s*(td|tds|touchdowns?)/i },
    { key: "season_rush_yds", re: /rush(ing)?\s*(yds|yards?)/i },
    { key: "season_rec_tds", re: /rec(eiving)?\s*(td|tds|touchdowns?)/i },
    { key: "season_rec_yds", re: /rec(eiving)?\s*(yds|yards?)/i },
    { key: "season_receptions", re: /\breceptions?\b|\bcatches\b/i }
  ];

  // Plausible season ranges; a line outside is refused, not clipped.
  var RANGES = {
    season_pass_yds: [500, 6000], season_pass_tds: [2, 60], season_rush_yds: [50, 2500],
    season_rush_tds: [0.5, 25], season_receptions: [5, 160], season_rec_yds: [50, 2300],
    season_rec_tds: [0.5, 20]
  };

  var NAME_ALIASES = { "kenny gainwell": "kenneth gainwell" };

  function normName(s) {
    var n = String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[.'’]/g, "").replace(/-/g, " ").replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "")
      .replace(/\s+/g, " ").trim();
    return NAME_ALIASES[n] || n;
  }

  function marketOf(text) {
    for (var i = 0; i < MARKETS.length; i += 1) if (MARKETS[i].re.test(text)) return MARKETS[i].key;
    return null;
  }

  var NUM = "(\\d{1,5}(?:\\.\\d+)?)";
  var OU_ONLY = new RegExp("^(o|over|u|under)\\s*" + NUM + "\\b", "i");
  var OU_INLINE = new RegExp("^(.+?)\\s+(o|over|u|under)\\s*" + NUM + "\\b(.*)$", "i");
  var ODDS_ONLY = /^\(?[+\-−]\d{2,4}\)?$/;
  var HAS_DIGIT = /\d/;

  // Looks like a person's name: 2-5 words of letters, no digits.
  function nameLike(line) {
    return !HAS_DIGIT.test(line) && /^[A-Za-z][A-Za-z.'’\- ]{2,40}$/.test(line) &&
      line.trim().split(/\s+/).length >= 2 && line.trim().split(/\s+/).length <= 5;
  }

  // players: {key: {name, pos?, team?}}. options: {season, snapshotDate}.
  // -> {ok, season, snapshotDate, rows: [{key, name, team, market, line,
  //    side, lineNo}], errors: [{lineNo, text, reason}], ignored}
  function parse(text, players, options) {
    var opts = options || {};
    var season = Number(opts.season);
    var byName = {};
    Object.keys(players || {}).forEach(function (k) { byName[normName(players[k].name)] = k; });
    var lines = String(text || "").replace(/\r/g, "").split("\n");
    var errors = [], found = {}, ignored = 0;
    var market = null, player = null, pendingName = null;

    function err(i, t, reason) { errors.push({ lineNo: i + 1, text: t, reason: reason }); }
    function record(i, t, k, mkt, side, value) {
      var r = RANGES[mkt];
      if (!(value >= r[0] && value <= r[1])) { err(i, t, "line " + value + " outside " + r[0] + "-" + r[1] + " for " + mkt); return; }
      var id = k + "|" + mkt;
      var prev = found[id];
      var over = /^o/i.test(side);
      if (prev && prev.over && over && prev.line !== value) {
        err(i, t, "two different over lines for " + players[k].name + " " + mkt + " (" + prev.line + ", " + value + ")");
        return;
      }
      if (!prev || (over && !prev.over)) found[id] = { key: k, market: mkt, line: value, over: over, lineNo: i + 1 };
    }

    lines.forEach(function (raw, i) {
      var t = raw.replace(/−/g, "-").replace(/\s+/g, " ").trim();
      if (!t) return;
      if (ODDS_ONLY.test(t)) return;
      var yr = t.match(/\b(20\d\d)(?:\s*[-–/]\s*(\d{2,4}))?\b/);
      var mkt = marketOf(t);
      if (mkt && !OU_INLINE.test(t)) {
        if (yr && season && Number(yr[1]) !== season) { err(i, t, "season " + yr[1] + " is not " + season); return; }
        market = mkt;
        // "Josh Allen - Regular Season Passing Yards": the player is named too.
        var head = t.split(/\s[-–|:]\s/)[0];
        player = byName[normName(head)] || null;
        pendingName = null;
        return;
      }
      var ou = t.match(OU_ONLY);
      if (ou) {
        if (!market) { err(i, t, "over/under before any market header"); return; }
        if (!player) { err(i, t, pendingName ? "unknown player: " + pendingName : "over/under with no player"); return; }
        record(i, t, player, market, ou[1], Number(ou[2]));
        return;
      }
      var inl = t.match(OU_INLINE);
      if (inl) {
        var nm = inl[1].replace(/\s[-–|:]\s.*$/, "");
        var k = byName[normName(nm)];
        var m2 = marketOf(inl[4]) || marketOf(inl[1]) || market;
        if (!k) { err(i, t, "unknown player: " + nm); return; }
        if (!m2) { err(i, t, "no market for this line"); return; }
        record(i, t, k, m2, inl[2], Number(inl[3]));
        return;
      }
      var key = byName[normName(t)];
      if (key) { player = key; pendingName = null; return; }
      if (nameLike(t)) { player = null; pendingName = t; ignored += 1; return; }
      if (HAS_DIGIT.test(t) && /\b(o|over|u|under)\b/i.test(t)) { err(i, t, "unreadable over/under line"); return; }
      ignored += 1;
    });

    var rows = Object.keys(found).map(function (id) {
      var f = found[id], p = players[f.key];
      return { key: f.key, name: p.name, team: p.team || null, market: f.market, line: f.line,
        side: f.over ? "over" : "under", lineNo: f.lineNo };
    }).sort(function (a, b) { return a.lineNo - b.lineNo; });
    return { ok: errors.length === 0 && rows.length > 0, season: season || null,
      snapshotDate: opts.snapshotDate || null, rows: rows, errors: errors, ignored: ignored };
  }

  // Parsed rows -> {playerKey: {market: line}}, the input vegasStatLine takes.
  function lineMap(rows) {
    var out = {};
    rows.forEach(function (r) { (out[r.key] = out[r.key] || {})[r.market] = r.line; });
    return out;
  }

  var VegasPaste = { parse: parse, lineMap: lineMap, normName: normName, MARKETS: MARKETS, RANGES: RANGES };
  root.VegasPaste = VegasPaste;
  if (typeof module !== "undefined" && module.exports) module.exports = VegasPaste;
})(typeof globalThis !== "undefined" ? globalThis : this);
