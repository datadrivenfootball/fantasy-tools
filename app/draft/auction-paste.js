// Auction draft results from a pasted platform page (JEG-1667): the third
// backtest auction (Jeremy, 2026-11-27: "Paste USO XVIII") and, later,
// league tendencies from prior drafts. Pure, no network.
//
// Player matching reuses the live site's roster matcher
// (app/v2/roster-paste.js: name index, nicknames, Yahoo "Det - RB" hints).
// This file only finds each sale's cost and keeper mark.
//
// Layouts read:
//   one line per sale:   "1  Jahmyr Gibbs  Det - RB  Fear Boners  $70"
//   (tabs or spaces; the team name and pick number are ignored)
//   or a sale over several lines: name / "Det - RB" / manager / "$70".
// A "K" or "(K)" or "Keeper" mark on the sale marks a keeper.
// Fails closed: a cost with no player before it, a player with no cost
// before the next player, a player sold twice, or a cost outside $0-$budget
// is an error and is listed. K and DEF sales are read and kept apart (the
// engine prices them at $1).
(function (root) {
  "use strict";

  var RP = root.DDFRosterPaste;
  if (!RP && typeof require === "function") RP = require("../v2/roster-paste.js");

  var COST = /\$\s?(\d{1,3})\b/g;
  var TEAM_POS = /\b([A-Z][A-Za-z]{1,3})\s*-\s*(QB|RB|WR|TE|K|DEF|D\/ST|DST)\b/;
  var KEEPER = /(^|\s|\()(K|Keeper)(\)|\s|$)/;
  // Nicknames the live matcher's NICK_MAP lacks (first word only).
  var NICKNAMES = { kenny: "Kenneth" };
  function expandNick(name) {
    var w = name.split(" ");
    var n = NICKNAMES[w[0].toLowerCase()];
    return n ? [n].concat(w.slice(1)).join(" ") : name;
  }

  // players: engine rows [{player_key, name, pos, team}]. options: {budget}.
  // -> {ok, sales: [{key, name, pos, price, keeper, lineNo}], kdef: [{text,
  //    price, keeper}], errors: [{lineNo, text, reason}], total, keepers}
  function parse(text, players, options) {
    var opts = options || {};
    var budget = Number(opts.budget) || 200;
    var index = RP.buildIndex(players || []);
    var lines = String(text || "").replace(/\r/g, "").split("\n");
    var errors = [], sales = [], kdef = [], seen = {};
    var pending = null; // the player waiting for his cost

    function err(i, t, reason) { errors.push({ lineNo: i + 1, text: t, reason: reason }); }
    function close(i, price, t, keeper) {
      if (!pending) { err(i, t, "cost with no player before it"); return; }
      if (!(price >= 0 && price <= budget)) { err(i, t, "cost $" + price + " outside $0-$" + budget); pending = null; return; }
      var isKeeper = keeper || pending.keeper;
      if (pending.kdef) {
        kdef.push({ text: pending.text, price: price, keeper: isKeeper });
      } else if (seen[pending.key]) {
        err(pending.lineNo - 1, pending.text, "sold twice: " + pending.name);
      } else {
        seen[pending.key] = true;
        sales.push({ key: pending.key, name: pending.name, pos: pending.pos, price: price, keeper: isKeeper,
          lineNo: pending.lineNo });
      }
      pending = null;
    }
    // A player named on this line (or null): the live matcher with the
    // line's own team/position hint.
    function playerOn(t, prev) {
      var tp = t.match(TEAM_POS);
      var before = tp ? t.slice(0, tp.index).trim() : t;
      // "Det - RB" on its own line: the name is the line above.
      if (tp && !before.replace(/^\s*\d{1,3}[.)]?\s*/, "") && prev) before = prev;
      var namePart = before.replace(COST, " ")
        .replace(/^\s*\d{1,3}[.)]?\s+/, "").replace(/\s+(K|\(K\)|Keeper)\s*$/i, "").trim();
      namePart = RP.cleanYahooName ? RP.cleanYahooName(namePart) : namePart;
      var pos = tp ? tp[2].replace(/D\/ST|DST/, "DEF") : null;
      if (pos === "K" || pos === "DEF") return { kdef: true, text: t };
      if (!namePart || /\d/.test(namePart)) return null;
      var hit = RP.matchCandidate({ name: expandNick(namePart), posHint: pos, teamHint: tp ? RP.normTeam(tp[1]) : null }, index, {});
      if (hit && hit.match) return { key: String(hit.match.player_key), name: hit.match.name, pos: hit.match.pos };
      return tp ? { unknown: namePart } : null;
    }

    var prev = null; // the last plain line (a possible name for "Det - RB")
    lines.forEach(function (raw, i) {
      var t = raw.replace(/\t+/g, "  ").replace(/\s+/g, " ").trim();
      if (!t) return;
      var costs = [];
      var m;
      COST.lastIndex = 0;
      while ((m = COST.exec(t))) costs.push(Number(m[1]));
      var p = playerOn(t, prev);
      var isPlain = !costs.length && !TEAM_POS.test(t);
      var keeper = KEEPER.test(t.replace(TEAM_POS, " "));
      if (p && (p.key || p.kdef)) {
        if (pending) err(pending.lineNo - 1, pending.text, "no cost before the next player");
        pending = { key: p.key, name: p.name, pos: p.pos, kdef: !!p.kdef, text: t, lineNo: i + 1, keeper: keeper };
        if (costs.length) close(i, costs[costs.length - 1], t, keeper);
        return;
      }
      if (p && p.unknown) {
        if (pending) err(pending.lineNo - 1, pending.text, "no cost before the next player");
        err(i, t, "unknown player: " + p.unknown);
        pending = null;
        return;
      }
      if (costs.length) { close(i, costs[costs.length - 1], t, keeper); prev = null; return; }
      if (pending && keeper && /^\(?(K|Keeper)\)?$/i.test(t)) { pending.keeper = true; return; }
      // A plain line right after a player is his manager, not a new name.
      if (isPlain && !pending) prev = t;
    });
    if (pending) err(pending.lineNo - 1, pending.text, "no cost before the end of the paste");

    var total = sales.reduce(function (s, x) { return s + x.price; }, 0) +
      kdef.reduce(function (s, x) { return s + x.price; }, 0);
    return { ok: errors.length === 0 && sales.length > 0, sales: sales, kdef: kdef, errors: errors,
      total: total, keepers: sales.filter(function (s) { return s.keeper; }).length };
  }

  var AuctionPaste = { parse: parse };
  root.AuctionPaste = AuctionPaste;
  if (typeof module !== "undefined" && module.exports) module.exports = AuctionPaste;
})(typeof globalThis !== "undefined" ? globalThis : this);
