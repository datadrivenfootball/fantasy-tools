/* Sleeper league import for connect.html (JEG-1570). Sleeper rosters are public: with a league link or ID the browser
 * reads the league from Sleeper's public read-only API (api.sleeper.app/v1) and builds the same league a pasted
 * rosters page gives (DDF.leaguePaste), so every later step is unchanged. Calls go from the browser to Sleeper only
 * (4 per load: state, league, users, rosters); nothing is sent anywhere else and nothing new is stored.
 *
 * Player names: sleeper-players.json (built by build_root_pages.py from data/inputs/sleeper_identity_base.json, the
 * same Sleeper identity table the data pipeline uses), {p: {sleeper_id: [name, pos, team]}}. Each team becomes the
 * lines a rosters page would show ("Josh Allen QB BUF"), read by the live matcher, so names match exactly as a paste.
 * Defenses are team codes ("KC") and are shown as not evaluated, as on a paste.
 *
 * DDF.sleeper.parseId(text)        -> league ID string or null (sleeper.com / sleeper.app links, bare ID, query strings)
 * DDF.sleeper.load(id, opts)       -> Promise<{ok, result, settings} | {ok:false, code, season?}>
 *     result: a DDF.leaguePaste result (teams, league {leagueName, leagueId, platform:'sleeper'}, ...)
 *     settings: {scoring, teams, superflex, roster:{QB,RB,WR,TE,FLEX,BENCH}} read from the league, or null
 *     code: 'invalid' | 'notfound' | 'oldseason' | 'empty' | 'network'
 *     opts: {fetch, rows, table, playersUrl} (fetch is injectable for tests)
 * DDF.sleeper.MESSAGES[code](info)  -> the plain-words message for an error
 */
(function (root) {
  "use strict";
  var API = "https://api.sleeper.app/v1/";
  var players = null;

  function parseId(text) {
    var t = String(text || "").trim();
    if (!t) return null;
    var m = /sleeper\.(?:com|app)\/leagues\/(\d{6,20})/i.exec(t) || /^(\d{6,20})$/.exec(t.replace(/[?#].*$/, "").replace(/\/+$/, ""));
    return m ? m[1] : null;
  }

  var MESSAGES = {
    invalid: function () { return "We could not find a Sleeper league ID in that. Paste your league link from the Sleeper app, or just the long number."; },
    notfound: function () { return "We could not find a Sleeper league with that ID. Check the number in your league link and try again."; },
    oldseason: function (i) { return "That league is from the " + (i && i.season ? i.season : "last") + " season. Open your league in the Sleeper app for this season and copy its link or ID."; },
    empty: function () { return "That Sleeper league has no rosters yet. Once the draft is done, try again."; },
    network: function () { return "We could not reach Sleeper just now. Check your connection and try again, or paste the rosters page instead."; }
  };

  function getJSON(f, url) {
    return f(url).then(function (r) {
      if (r.status === 404) return null;
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    });
  }
  function loadPlayers(f, url) {
    if (players) return Promise.resolve(players);
    return getJSON(f, url || "sleeper-players.json").then(function (j) { players = (j && j.p) || {}; return players; });
  }

  function settingsOf(lg) {
    if (!lg) return null;
    var pos = Array.isArray(lg.roster_positions) ? lg.roster_positions : [];
    var count = function (list) { return pos.filter(function (p) { return list.indexOf(p) >= 0; }).length; };
    var rec = lg.scoring_settings && Number(lg.scoring_settings.rec);
    var scoring = rec >= 1 ? "ppr" : rec >= 0.5 ? "half_ppr" : "standard";
    var roster = {QB: count(["QB"]), RB: count(["RB"]), WR: count(["WR"]), TE: count(["TE"]),
      FLEX: count(["FLEX", "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX", "RBTE_FLEX"]), BENCH: count(["BN"])};
    Object.keys(roster).forEach(function (k) { roster[k] = Math.min(20, roster[k]); });
    var out = {scoring: scoring, superflex: count(["SUPER_FLEX"]) > 0, roster: roster};
    var n = Number(lg.total_rosters);
    if ([8, 10, 12, 14].indexOf(n) >= 0) out.teams = n;
    return out;
  }

  /* the rosters page a paste would give: team name, then one line per player */
  function asPaste(users, rosters, map) {
    var byUser = {};
    (users || []).forEach(function (u) { if (u && u.user_id) byUser[u.user_id] = u; });
    var used = {}, names = [], lines = [], unknown = {};
    (rosters || []).slice().sort(function (a, b) { return (a.roster_id || 0) - (b.roster_id || 0); }).forEach(function (r, i) {
      var u = byUser[r.owner_id] || null;
      var name = String((u && u.metadata && u.metadata.team_name) || (u && u.display_name) || ("Team " + (r.roster_id || i + 1))).replace(/\s+/g, " ").trim().slice(0, 40);
      var key = name.toLowerCase(), n = 2;
      while (used[key]) { name = name.slice(0, 36) + " (" + n++ + ")"; key = name.toLowerCase(); }
      used[key] = 1;
      names.push(name);
      lines.push(name);
      (r.players || []).forEach(function (id) {
        var p = map[String(id)];
        if (p) lines.push(p[0] + " " + p[1] + (p[2] ? " " + p[2] : ""));
        else if (/^[A-Z]{2,3}$/.test(String(id))) lines.push(String(id) + " Defense DEF");
        else (unknown[name] = unknown[name] || []).push("Sleeper player " + id);   /* not in the identity table yet */
      });
    });
    return {names: names, text: lines.join("\n"), unknown: unknown};
  }

  function load(id, opts) {
    opts = opts || {};
    var f = opts.fetch || (root.fetch && root.fetch.bind(root));
    if (!id) return Promise.resolve({ok: false, code: "invalid"});
    var base = API + "league/" + encodeURIComponent(id);
    return Promise.all([getJSON(f, base), getJSON(f, base + "/users"), getJSON(f, base + "/rosters"), getJSON(f, API + "state/nfl")])
      .then(function (got) {
        var lg = got[0], users = got[1], rosters = got[2], state = got[3];
        if (!lg) return {ok: false, code: "notfound"};
        var current = state && (state.league_season || state.season);
        if (current && lg.season && String(lg.season) < String(current)) return {ok: false, code: "oldseason", season: String(lg.season)};
        if (!Array.isArray(rosters) || rosters.filter(function (r) { return r && (r.players || []).length; }).length < 2) return {ok: false, code: "empty"};
        return loadPlayers(f, opts.playersUrl).then(function (map) {
          var page = asPaste(users, rosters, map);
          var res = root.DDF.leaguePaste.readWithNames(page.text, page.names, opts.rows || [], {table: opts.table});
          res.teams.forEach(function (t) {
            (page.unknown[t.name] || []).forEach(function (line) { t.unmatched.push({line: line, reason: "missing", pos: ""}); res.missing++; });
          });
          res.site = "sleeper";
          res.strategy = "sleeper-api";
          res.league = {leagueName: lg.name ? String(lg.name).slice(0, 60) : null, leagueId: String(id), platform: "sleeper", confidence: 1};
          if (!res.ok) return {ok: false, code: "empty"};
          return {ok: true, result: res, settings: settingsOf(lg)};
        });
      }, function () { return {ok: false, code: "network"}; })
      .catch(function () { return {ok: false, code: "network"}; });
  }

  var api = {parseId: parseId, load: load, settingsOf: settingsOf, asPaste: asPaste, MESSAGES: MESSAGES, _reset: function () { players = null; }};
  root.DDF = root.DDF || {};
  root.DDF.sleeper = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
