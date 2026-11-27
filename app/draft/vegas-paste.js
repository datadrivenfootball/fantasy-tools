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
  // Floors sit above any single-game line (review of bc19862: a game prop of
  // 55.5 receiving yards or 6.5 receptions passed the old season floors).
  var RANGES = {
    season_pass_yds: [1500, 6000], season_pass_tds: [8, 60], season_rush_yds: [200, 2500],
    season_rush_tds: [1.5, 25], season_receptions: [15, 160], season_rec_yds: [200, 2300],
    season_rec_tds: [1.5, 20]
  };

  var NAME_ALIASES = { "kenny gainwell": "kenneth gainwell" };

  function normName(s) {
    var n = String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[.'’]/g, "").replace(/-/g, " ").replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "")
      .replace(/\s+/g, " ").trim();
    return NAME_ALIASES[n] || n;
  }

  // Stat families and stat types a header can name. A header naming more
  // than one family (passing, rushing, receiving) or more than one type
  // (yards, TDs, receptions) is a combined market, in any word order.
  var FAMILIES = [/\bpass(ing)?\b/i, /\brush(ing)?\b/i, /\brec(eiving)?\b(?!\w)|\breceiving\b/i];
  var TYPES = [/\byards?\b|\byds\b/i, /\btouchdowns?\b|\btds?\b/i, /\breceptions?\b|\bcatches\b/i];
  // Markets we refuse outright: their numbers fit a supported market's
  // range and would be stored as the wrong stat (reviews of f662c66, f0fcfb1).
  var REFUSED = [
    { re: /\b(1st|2nd|first|second)\s+half\b|\bhalf\b|\bquarter\b|\b[1-4](st|nd|rd|th)\s+q(uarter)?\b|\bq[1-4]\b/i, why: "half or quarter market" },
    { re: /\bplayoffs?\b|\bpost[- ]?season\b|\bincl\.?(?=\s|$)|\bincluding\b/i, why: "market that includes the playoffs" },
    { re: /\bweeks?\b|\bwk\s*\d|\bgames?\b|\bper game\b|\btonight\b|\bvs\.?\s|\s@\s/i, why: "weekly or game market" },
    { re: /\blong(est)?\b/i, why: "longest-play market" },
    { re: /\battempts?\b|\batt\b|\bcarries\b/i, why: "attempts market" },
    { re: /\btargets?\b/i, why: "targets market" },
    { re: /\bcompletions?\b|\bcomp\b/i, why: "completions market" },
    { re: /\binterceptions?\b|\bints?\b/i, why: "interceptions market" },
    { re: /\bsacks?\b|\bfumbles?\b|\btackles?\b|\bfantasy points\b|\bpoints\b/i, why: "unsupported stat" },
    { re: /\bleader\b|\bmost\b|\bmvp\b|\baward\b|\bto (score|record|lead)\b/i, why: "leader or award market" }
  ];
  // Words that make a line a market header (supported or not).
  var STATLIKE = /\b(yards?|yds|touchdowns?|tds?|receptions?|catches|attempts?|att|carries|targets?|completions?|interceptions?|ints?|longest|sacks?|fumbles?|tackles?|points|passing|rushing|receiving)\b/i;
  // A line that starts a weekly or game section (no stat named): everything
  // under it is refused until the next market header.
  var SECTION_BREAK = /\bweeks?\b|\bgame lines\b|\bgame props\b|\btonight\b|\b(sunday|monday|thursday|saturday) (night|games?)\b|\b[A-Z][a-z]+ (vs\.?|@) [A-Z][a-z]+\b/i;
  var SEASON = /\bseason\b|\bseason[- ]long\b|\bfull[- ]season\b/i;

  function count(res, t) { return res.reduce(function (n, re) { return n + (re.test(t) ? 1 : 0); }, 0); }

  function marketOf(text) {
    for (var i = 0; i < MARKETS.length; i += 1) if (MARKETS[i].re.test(text)) return MARKETS[i].key;
    return null;
  }
  // -> null (not a header) | {market, season} | {refused}
  function headerOf(text) {
    if (!STATLIKE.test(text)) return null;
    var t = text.replace(/\breceptions?\b/ig, " receptions ");
    var fam = count(FAMILIES, t.replace(/\breceptions?\b/ig, " ")), typ = count(TYPES, t);
    if (fam > 1 || typ > 1 || (fam >= 1 && /\breceptions?\b|\bcatches\b/i.test(t) && /\b(pass|rush)/i.test(t))) {
      return { refused: "combined market" };
    }
    for (var i = 0; i < REFUSED.length; i += 1) if (REFUSED[i].re.test(text)) return { refused: REFUSED[i].why };
    var m = marketOf(text);
    return m ? { market: m, season: SEASON.test(text) } : { refused: "unsupported market" };
  }

  var NUM = "(\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d{1,5}(?:\\.\\d+)?)";
  var OU_ONLY = new RegExp("^(o|over|u|under)\\s*" + NUM + "(?![\\d,])", "i");
  var OU_INLINE = new RegExp("^(.+?)\\s+(o|over|u|under)\\s*" + NUM + "(?![\\d,])(.*)$", "i");
  var ODDS_ONLY = /^\(?[+\-−]\d{2,4}\)?$/;
  // "CIN - WR" under a name is a team/position line and keeps the player.
  // A bare "CIN" or "JSN" does not: it may stand for another player.
  var TEAM_POS_ONLY = /^[A-Z]{2,4}\s*[-–·•|]\s*(QB|RB|WR|TE)$|^(QB|RB|WR|TE)$/;
  var SIDE_ONLY = /^(o|over|u|under)$/i;
  var NUM_ONLY = /^(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,5}(?:\.\d+)?)$/;
  var HAS_DIGIT = /\d/;
  var toNum = function (s) { return Number(String(s).replace(/,/g, "")); };
  // "Jaxon Smith-Njigba (SEA)", "Josh Allen - BUF" -> the bare name.
  function stripTeam(t) {
    return t.replace(/\s*\((?:[A-Z]{2,4}|[A-Z]{2,4}\s*[-–]\s*(QB|RB|WR|TE))\)\s*$/, "")
      .replace(/\s+[-–·•]\s+[A-Z]{2,4}$/, "").trim();
  }
  function nameLike(line) {
    return !HAS_DIGIT.test(line) && /^[A-Za-z][A-Za-z.'’\- ]{2,40}$/.test(line) &&
      line.trim().split(/\s+/).length >= 2 && line.trim().split(/\s+/).length <= 5;
  }
  var OU_GAP = 0.05; // over and under for one market more than 5% apart

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
    // The current section: its market (or why it is refused), whether it
    // carries a season marker, and the selected player.
    var market = null, refused = null, sectionSeason = false, player = null, pendingName = null;
    var pendingSide = null; // FanDuel style: "Over" on one line, "1375.5" on the next

    function err(i, t, reason) { errors.push({ lineNo: i + 1, text: t, reason: reason }); }
    function lookup(t) { return byName[normName(stripTeam(t))]; }
    function record(i, t, k, mkt, side, value) {
      var r = RANGES[mkt];
      if (!(value >= r[0] && value <= r[1])) { err(i, t, "line " + value + " outside " + r[0] + "-" + r[1] + " for " + mkt); return; }
      var id = k + "|" + mkt;
      var f = found[id] || (found[id] = { key: k, market: mkt, over: null, under: null, lineNo: i + 1, lines: {} });
      var which = /^o/i.test(side) ? "over" : "under";
      if (f[which] !== null && f[which] !== value) {
        err(i, t, "two different " + which + " lines for " + players[k].name + " " + mkt + " (" + f[which] + ", " + value + ")");
        return;
      }
      f[which] = value; f.lines[which] = i;
    }
    function startSection(hdr, t) {
      market = hdr && hdr.market ? hdr.market : null;
      refused = hdr && hdr.refused ? hdr.refused + " (" + t + ")" : null;
      sectionSeason = !!(hdr && hdr.season);
      pendingName = null;
    }

    lines.forEach(function (raw, i) {
      var t = raw.replace(/−/g, "-").replace(/\s+/g, " ").trim();
      if (!t) return;
      if (ODDS_ONLY.test(t)) return;
      if (pendingSide) {
        var side = pendingSide; pendingSide = null;
        if (NUM_ONLY.test(t)) t = side + " " + t;
        else err(i - 1, side, "over/under with no line after it");
      }
      if (SIDE_ONLY.test(t)) { pendingSide = t; return; }
      var yr = /©|copyright/i.test(t) ? null : t.match(/\b(20\d\d)\b/);
      // Two-digit season labels: "25/26 Regular Season" is the 2025 season.
      var yr2 = yr ? null : t.match(/\b(\d{2})\s*[\/–-]\s*(\d{2})\b/);
      if (!yr && yr2 && SEASON.test(t) && +yr2[2] === (+yr2[1] + 1) % 100) yr = [yr2[0], String(2000 + Number(yr2[1]))];
      if (yr && season && Number(yr[1]) !== season) {
        err(i, t, "season " + yr[1] + " is not " + season);
        startSection({ refused: "another season" }, t);
        player = null;
        return;
      }
      var inl = t.match(OU_INLINE);
      var hdr = inl ? null : headerOf(t);
      if (hdr) {
        startSection(hdr, t);
        // "Josh Allen - Regular Season Passing Yards": the player is named too.
        player = lookup(t.split(/\s[-–|:]\s/)[0]) || null;
        return;
      }
      if (!inl && SECTION_BREAK.test(t)) { startSection({ refused: "weekly or game section" }, t); player = null; return; }
      // Only a market header can mark its section as season-long; a menu
      // line ("Season Futures", "Game | Season Futures") never can.
      var ou = t.match(OU_ONLY);
      if (ou) {
        if (refused) { err(i, t, "not read, " + refused); return; }
        if (!market) { err(i, t, "over/under before any market header"); return; }
        if (!sectionSeason) { err(i, t, "market has no season marker (weekly or game lines?)"); return; }
        if (!player) { err(i, t, pendingName ? "unknown player: " + pendingName.text + " (line " + pendingName.lineNo + ")" : "over/under with no player"); return; }
        record(i, t, player, market, ou[1], toNum(ou[2]));
        return;
      }
      // One line holding player, over/under and number ("Jameson Williams
      // Over 55.5 Receiving Yards -110") is how single-game props print, so
      // it is refused; season markets list the player and the line apart.
      if (inl) { err(i, t, "one-line prop (looks like a single-game line)"); player = null; return; }
      if (TEAM_POS_ONLY.test(t)) return;
      if (/^[A-Z]{2,4}$/.test(t)) { player = null; pendingName = { text: t, lineNo: i + 1 }; ignored += 1; return; }
      if (HAS_DIGIT.test(t) && /\b(o|over|u|under)\b/i.test(t)) { err(i, t, "unreadable over/under line"); player = null; return; }
      var key = lookup(t);
      if (key) { player = key; pendingName = null; return; }
      // Anything else clears the selected player, so an unknown name can
      // never hand its lines to the player above it.
      player = null;
      if (nameLike(stripTeam(t))) pendingName = { text: t, lineNo: i + 1 };
      ignored += 1;
    });

    if (pendingSide) err(lines.length - 1, pendingSide, "over/under with no line after it");
    Object.keys(found).forEach(function (id) {
      var f = found[id];
      if (f.over !== null && f.under !== null && Math.abs(f.over - f.under) > OU_GAP * Math.min(f.over, f.under)) {
        err(f.lines.under, "O " + f.over + " / U " + f.under, "over and under more than 5% apart for " + players[f.key].name + " " + f.market);
      }
    });

    var rows = Object.keys(found).map(function (id) {
      var f = found[id], p = players[f.key];
      return { key: f.key, name: p.name, team: p.team || null, market: f.market,
        line: f.over !== null ? f.over : f.under, side: f.over !== null ? "over" : "under", lineNo: f.lineNo };
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

  var VegasPaste = { parse: parse, lineMap: lineMap, normName: normName, headerOf: headerOf, MARKETS: MARKETS, RANGES: RANGES, REFUSED: REFUSED };
  root.VegasPaste = VegasPaste;
  if (typeof module !== "undefined" && module.exports) module.exports = VegasPaste;
})(typeof globalThis !== "undefined" ? globalThis : this);
