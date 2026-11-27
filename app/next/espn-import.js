/* ESPN public league import for connect.html (league entry, Jeremy 2026-11-24: cheap wins first). A public ESPN league
 * loads from its ID alone: the browser reads ESPN's league data service (lm-api-reads.fantasy.espn.com, the one ESPN's
 * own site uses) and builds the same league a pasted rosters page gives (DDF.leaguePaste), so every later step is
 * unchanged. Measured from the live site (research, 2026-11-24): ESPN answers our origin (Access-Control-Allow-Origin
 * echoed), a public 12-team league with rosters is 830 KB compressed in about 0.3 s, a private league is 401, an
 * unknown ID 404.
 *
 * Calls go from the browser to ESPN only, without credentials (no cookies, no custom headers, so no preflight):
 *   1. view=mSettings                  (about 8 KB: league name, size, scoring, lineup slots), then
 *   2. view=mTeam&view=mRoster         (team names and every roster).
 * Nothing is sent anywhere else. Nothing new is stored: connect.html keeps {v:2, platform, id} as for any league ID.
 *
 * Players: each team becomes the lines a rosters page would show ("Bijan Robinson RB ATL"), read by the live matcher,
 * so names match exactly as a paste or a Sleeper import. Defenses become "CHI Defense DEF" and kickers "Name K TEAM":
 * the shipped kicker and defense matching marks them not evaluated.
 *
 * DDF.espn.parseId(text)        -> {id, season} or null (fantasy.espn.com links with leagueId=, or a bare 4-12 digit ID)
 * DDF.espn.load(id, opts)       -> Promise<{ok, result, settings} | {ok:false, code, status?}>
 *     result: a DDF.leaguePaste result (teams, league {leagueName, leagueId, platform:'espn'}, fit, ...)
 *     settings: {scoring, teams, superflex, superflexSlots?, roster:{QB,RB,WR,TE,FLEX,BENCH,K,DST}} as sleeper-import.js
 *     code: 'invalid' | 'private' (401/403) | 'notfound' (404) | 'empty' | 'timeout' | 'network'
 *     opts: {fetch, rows, table, season, now, timeoutMs, onProgress} (fetch is injectable for tests)
 *       onProgress({step:'settings', name, teams}) after the first call
 * DDF.espn.MESSAGES[code](info)  -> the plain-words message for an error
 */
(function (root) {
  "use strict";
  var API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/";
  var TIMEOUT_MS = 8000;   /* the whole lookup; measured 0.3 s on broadband, about 3 s on 4G */

  /* ESPN proTeamId -> the team codes the player table uses (Sleeper style) */
  var PRO_TEAM = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN",
    11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI",
    22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU"};
  /* defaultPositionId -> position */
  var POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"};
  /* lineupSlotCounts keys (ESPN lineup slot ids) */
  var SLOT = {QB: 0, RB: 2, RBWR: 3, WR: 4, WRTE: 5, TE: 6, OP: 7, DST: 16, K: 17, BENCH: 20, IR: 21, FLEX: 23};
  var REC_STAT = 53;   /* scoring statId for a reception */
  var IDP_SLOTS = [8, 9, 10, 11, 12, 13, 14, 15];   /* DT, DE, LB, DL, CB, S, DB, DP: defensive players, not valued */

  function seasonNow(now) {
    var d = now ? new Date(now) : new Date();
    return d.getMonth() < 2 ? d.getFullYear() - 1 : d.getFullYear();   /* January and February finish last season */
  }

  function parseId(text) {
    var t = String(text || "").trim();
    if (!t) return null;
    var season = /[?&]seasonId=(\d{4})\b/i.exec(t);
    var m = /[?&]leagueId=(\d{1,12})\b/i.exec(t) || /^(\d{4,12})$/.exec(t.replace(/[?#].*$/, "").replace(/\/+$/, ""));
    return m ? {id: m[1], season: season ? Number(season[1]) : null} : null;
  }

  var MESSAGES = {
    invalid: function () { return "We could not find an ESPN league ID in that. Paste your league link, or just the number after leagueId=."; },
    "private": function () { return "This ESPN league is private: ESPN shows it only to members who are signed in, so we need one copy from you."; },
    notfound: function (i) { return "We could not find an ESPN league with that ID for the " + ((i && i.season) || "current") + " season. Check the number after leagueId= in your league link."; },
    empty: function () { return "That ESPN league has no rosters yet. Once the draft is done, try again, or copy your rosters page."; },
    timeout: function () { return "ESPN is taking too long to answer. You can copy your rosters page instead."; },
    network: function () { return "We could not reach ESPN just now. You can copy your rosters page instead."; }
  };

  function leagueUrl(season, id, views) {
    return API + season + "/segments/0/leagues/" + encodeURIComponent(id) + "?" + views.map(function (v) { return "view=" + v; }).join("&");
  }
  /* GET without cookies; status codes the import understands become {status}, anything else throws */
  function getJSON(f, url, signal) {
    var init = {credentials: "omit", mode: "cors", cache: "no-store"};
    if (signal) init.signal = signal;
    return f(url, init).then(function (r) {
      if (r.status === 401 || r.status === 403 || r.status === 404) return {status: r.status};
      if (!r.ok) throw new Error("http " + r.status);
      return r.json().then(function (body) { return {status: r.status, body: body}; });
    });
  }

  function slotCounts(lg) {
    var c = lg && lg.settings && lg.settings.rosterSettings && lg.settings.rosterSettings.lineupSlotCounts;
    return c && typeof c === "object" ? c : null;
  }
  function recPoints(lg) {
    var items = lg && lg.settings && lg.settings.scoringSettings && lg.settings.scoringSettings.scoringItems;
    var item = (Array.isArray(items) ? items : []).filter(function (s) { return s && s.statId === REC_STAT; })[0];
    return item ? {points: Number(item.points) || 0, te: item.pointsOverrides && Number(item.pointsOverrides[SLOT.TE])} : {points: 0, te: NaN};
  }

  var SIZES = [8, 10, 12, 14];
  /* the size the values use: a count between sizes rounds up (9 -> 10), below 8 uses 8, above 14 uses 14 (Jeremy, 2026-11-24) */
  function closestSize(n) {
    for (var i = 0; i < SIZES.length; i++) if (SIZES[i] >= n) return SIZES[i];
    return SIZES[SIZES.length - 1];
  }

  /* the engine settings the league gives, in sleeper-import.js settingsOf's shape */
  function settingsOf(lg) {
    if (!lg || !lg.settings) return null;
    var c = slotCounts(lg) || {}, n = function (k) { var v = Number(c[SLOT[k]]); return isFinite(v) && v > 0 ? Math.floor(v) : 0; };
    var rec = recPoints(lg).points;
    var out = {scoring: rec >= 1 ? "ppr" : rec >= 0.5 ? "half_ppr" : "standard"};
    var roster = {QB: n("QB"), RB: n("RB"), WR: n("WR"), TE: n("TE"), FLEX: n("FLEX") + n("RBWR") + n("WRTE"), BENCH: n("BENCH")};
    Object.keys(roster).forEach(function (k) { roster[k] = Math.min(20, roster[k]); });
    roster.K = Math.min(3, n("K"));
    roster.DST = Math.min(3, n("DST"));
    var sf = n("OP");   /* OP is ESPN's superflex (QB, RB, WR or TE) */
    out.superflex = sf > 0;
    if (sf >= 2) out.superflexSlots = 2;
    if (slotCounts(lg) && roster.QB >= 1) out.roster = roster;
    var size = Number(lg.settings.size);
    if (isFinite(size) && size >= 2) out.teams = closestSize(size);
    return out;
  }
  /* what the league has that the values cannot reflect: a team count outside 8 to 14, TE premium, defensive player
     (IDP) slots (those players are left off the rosters: a name alone could match an offensive player) */
  function fitOf(lg) {
    if (!lg || !lg.settings) return null;
    var fit = {}, size = Number(lg.settings.size), rec = recPoints(lg), c = slotCounts(lg) || {};
    var idp = IDP_SLOTS.reduce(function (a, k) { var v = Number(c[k]); return a + (isFinite(v) && v > 0 ? Math.floor(v) : 0); }, 0);
    if (idp > 0) fit.idp = idp;
    if (isFinite(size) && size >= 2 && SIZES.indexOf(size) < 0) { fit.teams = size; fit.usedTeams = closestSize(size); }
    if (isFinite(rec.te) && rec.te > rec.points) fit.tePremium = Math.round((rec.te - rec.points) * 100) / 100;
    return Object.keys(fit).length ? fit : null;
  }

  function teamName(t, i) {
    var name = t && (t.name || [t.location, t.nickname].filter(Boolean).join(" ") || t.abbrev);
    return String(name || "").replace(/\s+/g, " ").trim().slice(0, 40) || "Team " + ((t && t.id) || i + 1);
  }
  /* one block per team: the lines a rosters page shows for it, read as a paste reads them */
  function asBlocks(teams) {
    var used = {};
    return (teams || []).slice().sort(function (a, b) { return (a.id || 0) - (b.id || 0); }).map(function (t, i) {
      var name = teamName(t, i), key = name.toLowerCase(), k = 2;
      while (used[key]) { name = Array.from(name).slice(0, 36).join("") + " (" + k++ + ")"; key = name.toLowerCase(); }
      used[key] = 1;
      var lines = [];
      ((t.roster && t.roster.entries) || []).forEach(function (e) {
        var p = e && e.playerPoolEntry && e.playerPoolEntry.player;
        if (!p) return;
        var pos = POS[p.defaultPositionId] || "", team = PRO_TEAM[p.proTeamId] || "";
        if (!pos) return;   /* defensive players (IDP), punters, head coaches: not valued, and not matched by name alone */
        if (pos === "DEF") { if (team) lines.push(team + " Defense DEF"); return; }
        var full = String(p.fullName || [p.firstName, p.lastName].filter(Boolean).join(" ")).replace(/\s+/g, " ").trim();
        if (full) lines.push(full + (pos ? " " + pos : "") + (team ? " " + team : ""));
      });
      return {name: name, text: lines.join("\n")};
    });
  }

  /* the league from ESPN's answers: lg carries settings, body carries teams with rosters (the same object when one
     call asked for all three views, as ESPN's data view does) */
  function fromLeague(lg, body, id, opts) {
    opts = opts || {};
    var blocks = asBlocks((body && body.teams) || []);
    if (blocks.filter(function (b) { return b.text; }).length < 2) return {ok: false, code: "empty"};
    var res = root.DDF.leaguePaste.fromBlocks(blocks, opts.rows || [], {table: opts.table, site: "espn", strategy: opts.strategy || "espn-api"});
    if (!res.ok) return {ok: false, code: "empty"};
    var name = lg && lg.settings && lg.settings.name;
    res.league = {leagueName: name ? String(name).slice(0, 60) : null, leagueId: id ? String(id) : null, platform: "espn", confidence: 1};
    res.fit = fitOf(lg);
    return {ok: true, result: res, settings: settingsOf(lg)};
  }

  function load(id, opts) {
    opts = opts || {};
    var f = opts.fetch || (root.fetch && root.fetch.bind(root));
    if (!id || !/^\d{1,12}$/.test(String(id))) return Promise.resolve({ok: false, code: "invalid"});
    var season = opts.season || seasonNow(opts.now);
    var ctl = typeof AbortController === "function" ? new AbortController() : null, timedOut = false, timer = null;
    var budget = new Promise(function (resolve) {
      timer = setTimeout(function () { timedOut = true; if (ctl) ctl.abort(); resolve({ok: false, code: "timeout"}); }, opts.timeoutMs || api.TIMEOUT_MS);
    });
    var signal = ctl ? ctl.signal : null;
    var work = getJSON(f, leagueUrl(season, id, ["mSettings"]), signal).then(function (got) {
      if (got.status === 401 || got.status === 403) return {ok: false, code: "private", status: got.status};
      if (got.status === 404) return {ok: false, code: "notfound", season: season};
      var lg = got.body || {};
      var size = Number(lg.settings && lg.settings.size);
      if (opts.onProgress) { try { opts.onProgress({step: "settings", name: lg.settings && lg.settings.name || null, teams: isFinite(size) ? size : null}); } catch (e) { /* progress only */ } }
      return getJSON(f, leagueUrl(season, id, ["mTeam", "mRoster"]), signal).then(function (got2) {
        if (got2.status === 401 || got2.status === 403) return {ok: false, code: "private", status: got2.status};
        if (got2.status === 404) return {ok: false, code: "notfound", season: season};
        return fromLeague(lg, got2.body, id, opts);
      });
    }).then(null, function () { return {ok: false, code: timedOut ? "timeout" : "network"}; });
    return Promise.race([work, budget]).then(function (out) { clearTimeout(timer); return out; });
  }

  var api = {parseId: parseId, load: load, fromLeague: fromLeague, settingsOf: settingsOf, fitOf: fitOf, asBlocks: asBlocks, seasonNow: seasonNow,
    leagueUrl: leagueUrl, MESSAGES: MESSAGES, TIMEOUT_MS: TIMEOUT_MS};
  root.DDF = root.DDF || {};
  root.DDF.espn = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
