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
 *     settings: {scoring, teams, superflex, superflexSlots?, roster:{QB,RB,WR,TE,FLEX,BENCH,K,DST}} read from the league, or null
 *       (superflexSlots: 2 when the league has 2+ SUPER_FLEX spots; DDF.engine.apply reads it)
 *     code: 'invalid' | 'notfound' | 'oldseason' | 'empty' | 'network'
 *     opts: {fetch, rows, table, playersUrl, leagueState, now, myTeamId} (fetch is injectable for tests)
 * DDF.sleeper.MESSAGES[code](info)  -> the plain-words message for an error
 *
 * League state (JEG-1656, part of JEG-1653; contract docs/contract/league-state-v1.md): load(id, {leagueState: true})
 * also returns leagueState, a league-state/1 document built from the same league, users and rosters responses plus one
 * public matchups call per remaining regular-season week (GET league/{id}/matchups/{week}). Without the option load is
 * unchanged (4 calls, no leagueState). A failed or empty matchups call makes the schedule null with a reason; it never
 * fails the import.
 * DDF.sleeper.buildLeagueState(lg, users, rosters, matchups, opts) -> league-state/1 object (pure; matchups = {week: rows|null})
 *     opts: {now (ISO, default now), myTeamId}
 * DDF.sleeper.remainingWeeks(lg, rosters) -> [week...] the matchups weeks load() fetches (empty when the window is unknown)
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
    return getJSON(f, url || "sleeper-players.json").then(function (j) {
      if (!j || !j.p) throw new Error("players");   /* not cached: the next try fetches again */
      players = j.p; return players;
    });
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
    /* JEG-1632: kicker and defense slots (engine keys K / DST, 0-3): not valued, but they take roster spots */
    roster.K = Math.min(3, count(["K"]));
    roster.DST = Math.min(3, count(["DEF"]));
    var sf = count(["SUPER_FLEX"]);
    var out = {scoring: scoring, superflex: sf > 0};
    if (sf >= 2) out.superflexSlots = 2;   /* JEG-1571: two QB-eligible flex slots (the site's most) */
    if (roster.QB >= 1) out.roster = roster;   /* a superflex-only lineup is left for settings.html to confirm */
    var n = Number(lg.total_rosters);
    if ([8, 10, 12, 14].indexOf(n) >= 0) out.teams = n;
    return out;
  }

  /* ---------- league state (JEG-1656) ---------- */
  function lsKnown(value, source, asOf) { return {value: value, source: source, as_of: asOf, reason: null}; }
  function lsMissing(reason) { return {value: null, source: null, as_of: null, reason: reason}; }
  function isWhole(x, lo, hi) { return typeof x === "number" && isFinite(x) && Math.floor(x) === x && x >= lo && x <= hi; }

  /* Sleeper trade_deadline: a week, or 99 for no deadline (verified on 2025 leagues: trades complete after week 14 only
     where it is 99). 0 and other values are not understood, so they are missing rather than guessed. */
  function tradeDeadline(set) {
    var d = set.trade_deadline;
    if (d === 99) return {value: "none", src: "sleeper:league.settings.trade_deadline (99 = no deadline)"};
    if (isWhole(d, 1, 22)) return {value: d, src: "sleeper:league.settings.trade_deadline"};
    return {value: null, reason: d === undefined || d === null ? "Sleeper did not return a trade deadline" : "Sleeper trade_deadline " + JSON.stringify(d) + " is not a week or 99, so it is not read"};
  }

  /* Byes from playoff_teams: the bracket fills to the next power of two. Verified against 2025 winners brackets
     (4 teams: 0 byes, 5: 3, 6: 2, 7: 1, 8: 0); other sizes are not verified, so they are missing. */
  function byesFor(n) {
    if (!isWhole(n, 4, 8)) return null;
    var size = 1; while (size < n) size *= 2;
    return size - n;
  }

  function remainingWindow(lg, rosters) {
    var set = (lg && lg.settings) || {};
    var start = set.playoff_week_start, through = null;
    if (isWhole(set.last_scored_leg, 0, 21)) through = {value: set.last_scored_leg, src: "sleeper:league.settings.last_scored_leg"};
    else if (lg && (lg.status === "pre_draft" || lg.status === "drafting") && Array.isArray(rosters) && rosters.length
      && rosters.every(function (r) { var s = r && r.settings; return s && s.wins === 0 && s.losses === 0 && s.ties === 0; })) {
      through = {value: 0, src: "derived:sleeper:league.status+rosters (preseason, every record 0-0-0)"};
    }
    var last = isWhole(start, 2, 22) ? start - 1 : null;
    if (through && last !== null && through.value > last) through = {value: last, src: through.src + ", capped at last_regular_week"};
    return {through: through, last: last};
  }

  function remainingWeeks(lg, rosters) {
    var w = remainingWindow(lg, rosters), out = [];
    if (!w.through || w.last === null) return out;
    for (var k = w.through.value + 1; k <= w.last; k++) out.push(k);
    return out;
  }

  /* rows for one week -> [{home, away}] pairing roster ids by matchup_id, or a string saying why not */
  function pairWeek(rows, ids) {
    if (!Array.isArray(rows)) return "Sleeper returned no matchups";
    if (!rows.length) return "Sleeper has not generated matchups for it yet";
    var by = Object.create(null), order = [];
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], id = r && String(r.roster_id);
      if (!r || ids[id] !== true) return "a matchup row has an unknown roster";
      if (r.matchup_id === null || r.matchup_id === undefined) return "a team has no matchup_id";
      if (!by[r.matchup_id]) { by[r.matchup_id] = []; order.push(r.matchup_id); }
      by[r.matchup_id].push(id);
    }
    var games = [];
    for (var j = 0; j < order.length; j++) {
      var g = by[order[j]];
      if (g.length !== 2) return "matchup " + order[j] + " does not pair two teams";
      games.push({home: g[0], away: g[1]});
    }
    return games;
  }

  function buildLeagueState(lg, users, rosters, matchups, opts) {
    opts = opts || {};
    var asOf = opts.now || new Date().toISOString();
    var set = (lg && lg.settings) || {};
    var meta = (lg && lg.metadata) || {};
    var sorted = (Array.isArray(rosters) ? rosters : []).slice().sort(function (a, b) { return (a.roster_id || 0) - (b.roster_id || 0); });
    var names = asBlocks(users, sorted, {});
    var ids = Object.create(null);
    var nDiv = isWhole(set.divisions, 1, 99) ? set.divisions : 0;
    var teams = sorted.map(function (r, i) {
      var id = String(r.roster_id), s = r.settings || {};
      ids[id] = true;
      var rec = isWhole(s.wins, 0, 99) && isWhole(s.losses, 0, 99) && isWhole(s.ties, 0, 99)
        ? lsKnown({w: s.wins, l: s.losses, t: s.ties}, "sleeper:rosters.settings.wins+losses+ties", asOf)
        : lsMissing("Sleeper roster has no wins, losses and ties");
      var pf = typeof s.fpts === "number" && s.fpts >= 0
        ? lsKnown(Math.round((s.fpts + (typeof s.fpts_decimal === "number" ? s.fpts_decimal / 100 : 0)) * 100) / 100, "sleeper:rosters.settings.fpts+fpts_decimal", asOf)
        : lsMissing("Sleeper roster has no fpts");
      var pa = typeof s.fpts_against === "number" && s.fpts_against >= 0
        ? lsKnown(Math.round((s.fpts_against + (typeof s.fpts_against_decimal === "number" ? s.fpts_against_decimal / 100 : 0)) * 100) / 100, "sleeper:rosters.settings.fpts_against+fpts_against_decimal", asOf)
        : lsMissing("Sleeper roster has no fpts_against (not returned before games are scored)");
      var div = !nDiv ? lsMissing("the league has no divisions")
        : isWhole(s.division, 1, nDiv)
          ? lsKnown(isText(meta["division_" + s.division]) ? String(meta["division_" + s.division]).trim() : "Division " + s.division, "sleeper:rosters.settings.division+league.metadata.division_N", asOf)
          : lsMissing("Sleeper roster has no division");
      return {id: id, name: names[i].name, record: rec, points_for: pf, points_against: pa, division: div};
    });

    var win = remainingWindow(lg, sorted);
    var through = win.through ? lsKnown(win.through.value, win.through.src, asOf)
      : lsMissing("Sleeper did not return last_scored_leg and the league is not in preseason");

    var schedule;
    var median = set.league_average_match === 1;
    if (!win.through || win.last === null) schedule = lsMissing("the remaining-week window is unknown (needs last_scored_leg and playoff_week_start)");
    else {
      var weeks = [], bad = null;
      for (var wk = win.through.value + 1; wk <= win.last && !bad; wk++) {
        var got = pairWeek(matchups ? matchups[wk] : undefined, ids);
        if (typeof got === "string") bad = "week " + wk + ": " + got;
        else weeks.push({week: wk, median_game: median, games: got});
      }
      schedule = bad ? lsMissing("Sleeper matchups unavailable, " + bad) : lsKnown(weeks, "sleeper:league/matchups/{week}", asOf);
    }

    var spots = isWhole(set.playoff_teams, 1, teams.length || 99) ? set.playoff_teams : null;
    var byes = spots === null ? null : byesFor(spots);
    var rules = {
      spots: spots !== null ? lsKnown(spots, "sleeper:league.settings.playoff_teams", asOf) : lsMissing("Sleeper did not return a usable playoff_teams"),
      start_week: isWhole(set.playoff_week_start, 2, 22) ? lsKnown(set.playoff_week_start, "sleeper:league.settings.playoff_week_start", asOf) : lsMissing("Sleeper did not return a usable playoff_week_start"),
      last_regular_week: win.last !== null ? lsKnown(win.last, "derived:sleeper:league.settings.playoff_week_start-1", asOf) : lsMissing("playoff_week_start is unknown"),
      byes: byes !== null ? lsKnown(byes, "derived:sleeper:league.settings.playoff_teams (bracket fills to a power of two)", asOf)
        : lsMissing(spots === null ? "playoff_teams is unknown" : "byes for a " + spots + "-team bracket are not verified"),
      /* playoff_seed_type (0 or 1) does not change who is seeded first: on 2025 brackets division winners were seeded first
         under both values whenever the league has divisions, and record decided it without divisions. */
      seeding_rule: lsKnown(nDiv > 0 ? "division_winners_first" : "record", "derived:sleeper:league.settings.divisions (absent or 0 = no divisions; playoff_seed_type does not change seeding)", asOf),
      tiebreak: lsMissing("Sleeper exposes no verified tiebreak setting (playoff_seed_type has no verified meaning)")
    };
    var td = tradeDeadline(set);

    var mine = opts.myTeamId !== undefined && opts.myTeamId !== null && ids[String(opts.myTeamId)] === true ? String(opts.myTeamId) : null;
    var state = {
      version: "league-state/1",
      league: {id: String((lg && lg.league_id) || opts.leagueId || ""), provider: "sleeper", capture: "import", season: Number(lg && lg.season)},
      captured_at: asOf,
      my_team_id: mine,
      teams: teams,
      record_through_week: through,
      schedule: schedule,
      playoff_rules: rules,
      trade_deadline_week: td.value !== null ? lsKnown(td.value, td.src, asOf) : lsMissing(td.reason)
    };
    if (mine === null) state.my_team_missing_reason = "a Sleeper league link does not say which team is yours";
    return state;
  }

  function isText(x) { return typeof x === "string" && x.trim().length > 0; }

  /* the first remaining week alone first: Sleeper has not generated matchups before the draft, so an empty first week
     ends the fetching (the schedule is null with that reason); otherwise the rest go out together */
  function fetchMatchups(f, base, weeks) {
    var out = {};
    function one(w) { return getJSON(f, base + "/matchups/" + w).then(function (rows) { out[w] = rows; }, function () { out[w] = null; }); }
    if (!weeks.length) return Promise.resolve(out);
    return one(weeks[0]).then(function () {
      if (!Array.isArray(out[weeks[0]]) || !out[weeks[0]].length) return out;
      return Promise.all(weeks.slice(1).map(one)).then(function () { return out; });
    });
  }

  /* one block per team: the lines a rosters page shows for it ("Josh Allen QB BUF"), read as a paste reads them */
  function asBlocks(users, rosters, map) {
    var byUser = {};
    (users || []).forEach(function (u) { if (u && u.user_id) byUser[u.user_id] = u; });
    var used = {}, out = [];
    (rosters || []).slice().sort(function (a, b) { return (a.roster_id || 0) - (b.roster_id || 0); }).forEach(function (r, i) {
      var u = byUser[r.owner_id] || null;
      var name = String((u && u.metadata && u.metadata.team_name) || (u && u.display_name) || "").replace(/\s+/g, " ").trim().slice(0, 40)
        || "Team " + (r.roster_id || i + 1);
      var key = name.toLowerCase(), n = 2;
      while (used[key]) { name = Array.from(name).slice(0, 36).join("") + " (" + n++ + ")"; key = name.toLowerCase(); }
      used[key] = 1;
      var lines = [], unknown = [];
      (r.players || []).forEach(function (id) {
        var p = map[String(id)];
        if (p) lines.push(p[0] + " " + p[1] + (p[2] ? " " + p[2] : ""));
        else if (/^[A-Z]{2,3}$/.test(String(id))) lines.push(String(id) + " Defense DEF");
        else unknown.push("A player not in our list yet (Sleeper id " + id + ")");
      });
      out.push({name: name, text: lines.join("\n"), unknown: unknown});
    });
    return out;
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
          var blocks = asBlocks(users, rosters, map);
          var res = root.DDF.leaguePaste.fromBlocks(blocks, opts.rows || [], {table: opts.table, site: "sleeper", strategy: "sleeper-api"});
          res.teams.forEach(function (t, i) {
            blocks[i].unknown.forEach(function (line) { t.unmatched.push({line: line, reason: "missing", pos: ""}); res.missing++; });
          });
          res.league = {leagueName: lg.name ? String(lg.name).slice(0, 60) : null, leagueId: String(id), platform: "sleeper", confidence: 1};
          if (!res.ok) return {ok: false, code: "empty"};
          var out = {ok: true, result: res, settings: settingsOf(lg)};
          if (!opts.leagueState) return out;
          return fetchMatchups(f, base, remainingWeeks(lg, rosters)).then(function (m) {
            out.leagueState = buildLeagueState(lg, users, rosters, m, {now: opts.now, myTeamId: opts.myTeamId, leagueId: String(id)});
            return out;
          });
        });
      }, function () { return {ok: false, code: "network"}; })
      .catch(function () { return {ok: false, code: "network"}; });
  }

  var api = {parseId: parseId, load: load, settingsOf: settingsOf, buildLeagueState: buildLeagueState, remainingWeeks: remainingWeeks, asBlocks: asBlocks, MESSAGES: MESSAGES, _reset: function () { players = null; }};
  root.DDF = root.DDF || {};
  root.DDF.sleeper = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
