// League settings loader for the DDF auction draft tool (JEG-1672, Phase 1
// child of JEG-1667). Reads league settings from Sleeper (public API) or ESPN
// (public read endpoint) and falls back to a paste parser for Yahoo or private
// leagues. Pure; no DOM; UMD (browser: window.DraftLeague, Node: require).
//
// API:
//   parseRef(text)             -> {platform, id, season?} or null
//   settingsUrl(ref)           -> string URL for the platform settings page
//   load(ref, {fetch, season}) -> Promise<{ok, league} | {ok:false, code, settingsUrl, message}>
//   fromSleeper(lg, users, drafts) -> league (pure converter)
//   fromEspn(json)             -> league (pure converter)
//   parsePaste(text)           -> {ok, platform, league, found, missing, unread}
//
// League shape:
//   {platform, leagueId, name, teams:[{name, budget}], budget, minBid,
//    slots:{QB,RB,WR,TE,FLEX,SUPERFLEX,K,DST,BN},
//    scoring:{pass_yds,pass_tds,ints,rush_yds,rush_tds,rec,rec_yds,rec_tds,fum_lost},
//    scoringLabel, notes:[]}
//
// Plain GETs only: no cookies, tokens, or custom auth headers are ever sent.
(function (root) {
  "use strict";

  // ---- defaults -------------------------------------------------------

  var DEFAULT_SCORING = {
    pass_yds: 0.04, pass_tds: 4, ints: -2,
    rush_yds: 0.1,  rush_tds: 6,
    rec: 0,         rec_yds: 0.1, rec_tds: 6,
    fum_lost: -2
  };

  var DEFAULT_SLOTS = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, K: 1, DST: 1, BN: 6 };

  // ---- parseRef -------------------------------------------------------

  // Accepts league URLs from each platform and bare IDs.
  // Bare 17+ digit number = Sleeper; shorter all-digit = ESPN.
  function parseRef(text) {
    var t = String(text || "").trim();
    if (!t) return null;

    // Sleeper URL: sleeper.com/leagues/<id> or sleeper.app/leagues/<id>
    var m = /sleeper\.(?:com|app)\/leagues\/(\d{6,20})/i.exec(t);
    if (m) return { platform: "sleeper", id: m[1] };

    // ESPN URL: fantasy.espn.com/football/...?leagueId=<id>[&seasonId=<year>]
    m = /fantasy\.espn\.com\/football\/[^?#]*[?&]leagueId=(\d+)/i.exec(t);
    if (m) {
      var ref = { platform: "espn", id: m[1] };
      var sy = /[?&]seasonId=(\d{4})/i.exec(t);
      if (sy) ref.season = sy[1];
      return ref;
    }

    // Yahoo URL: football.fantasysports.yahoo.com/f1/<id>
    m = /football\.fantasysports\.yahoo\.com\/f1\/(\d+)/i.exec(t);
    if (m) return { platform: "yahoo", id: m[1] };

    // Bare ID: 17+ digits = Sleeper; shorter all-digit = ESPN
    var bare = t.replace(/[?#].*$/, "").replace(/\/+$/, "").trim();
    if (/^\d+$/.test(bare)) {
      if (bare.length >= 17) return { platform: "sleeper", id: bare };
      if (bare.length >= 3)  return { platform: "espn",    id: bare };
    }

    return null;
  }

  // ---- settingsUrl ----------------------------------------------------

  function settingsUrl(ref) {
    if (!ref) return null;
    var id = String(ref.id || "");
    switch (ref.platform) {
      case "espn":    return "https://fantasy.espn.com/football/league/settings?leagueId=" + id;
      case "yahoo":   return "https://football.fantasysports.yahoo.com/f1/" + id + "/settings";
      case "sleeper": return "https://sleeper.com/leagues/" + id + "/settings";
    }
    return null;
  }

  // ---- load -----------------------------------------------------------

  // Fetches league settings from the platform's public read API.
  // opts.fetch: injectable fetch (required for Node; default globalThis.fetch)
  // opts.season: year string for ESPN (default current year from Date)
  // Plain GETs only; no credentials, cookies or custom headers are sent.
  function load(ref, opts) {
    opts = opts || {};
    if (!ref || !ref.platform) return Promise.resolve({ ok: false, code: "notfound", settingsUrl: null, message: "No league reference" });
    var su = settingsUrl(ref);

    if (ref.platform === "yahoo") {
      return Promise.resolve({ ok: false, code: "paste", settingsUrl: su, message: "Yahoo requires sign-in; paste your league settings instead." });
    }

    var fetch = opts.fetch || (typeof globalThis !== "undefined" && globalThis.fetch);
    if (!fetch) return Promise.resolve({ ok: false, code: "network", settingsUrl: su, message: "fetch is not available; pass opts.fetch" });

    if (ref.platform === "sleeper") return _loadSleeper(ref, fetch, su);
    if (ref.platform === "espn")    return _loadEspn(ref, fetch, su, opts);

    return Promise.resolve({ ok: false, code: "notfound", settingsUrl: su, message: "Unknown platform" });
  }

  function _get(fetch, url) {
    // Plain GET; no credentials, tokens or custom auth headers.
    return fetch(url).then(function (r) {
      return { status: r.status, json: function () { return r.json(); } };
    });
  }

  function _loadSleeper(ref, fetch, su) {
    var base = "https://api.sleeper.app/v1/league/" + ref.id;
    var lgP    = _get(fetch, base);
    var usersP = _get(fetch, base + "/users");
    var draftsP = _get(fetch, base + "/drafts");

    return Promise.all([lgP, usersP, draftsP]).then(function (results) {
      var lgR = results[0], usR = results[1], drR = results[2];

      if (lgR.status === 404) return { ok: false, code: "notfound", settingsUrl: su, message: "Sleeper league not found." };
      if (lgR.status !== 200) return { ok: false, code: "network",  settingsUrl: su, message: "Sleeper returned HTTP " + lgR.status };

      return lgR.json().then(function (lg) {
        if (!lg || !lg.league_id) return { ok: false, code: "notfound", settingsUrl: su, message: "Sleeper returned no league data." };

        var usersP2 = usR.status === 200 ? usR.json() : Promise.resolve([]);
        var draftsP2 = drR.status === 200 ? drR.json() : Promise.resolve([]);

        return Promise.all([usersP2, draftsP2]).then(function (ud) {
          var league = fromSleeper(lg, ud[0] || [], ud[1] || []);
          return { ok: true, league: league };
        });
      });
    }).catch(function (e) {
      return { ok: false, code: "network", settingsUrl: su, message: "Network error: " + (e && e.message || e) };
    });
  }

  function _loadEspn(ref, fetch, su, opts) {
    var season = opts.season || String(new Date().getFullYear());
    var url = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/" +
      season + "/segments/0/leagues/" + ref.id + "?view=mSettings&view=mTeam";

    return _get(fetch, url).then(function (r) {
      if (r.status === 401 || r.status === 403) return { ok: false, code: "private", settingsUrl: su, message: "ESPN league is private; paste your league settings instead." };
      if (r.status === 404) return { ok: false, code: "notfound", settingsUrl: su, message: "ESPN league not found." };
      if (r.status !== 200) return { ok: false, code: "network",  settingsUrl: su, message: "ESPN returned HTTP " + r.status };

      return r.json().then(function (json) {
        var league = fromEspn(json);
        return { ok: true, league: league };
      });
    }).catch(function (e) {
      return { ok: false, code: "network", settingsUrl: su, message: "Network error: " + (e && e.message || e) };
    });
  }

  // ---- fromSleeper ----------------------------------------------------

  // Sleeper scoring_settings keys -> engine keys.
  var SLEEPER_SCORING = {
    pass_yd:  "pass_yds",
    pass_td:  "pass_tds",
    pass_int: "ints",   // stored as negative in Sleeper
    rush_yd:  "rush_yds",
    rush_td:  "rush_tds",
    rec:      "rec",
    rec_yd:   "rec_yds",
    rec_td:   "rec_tds",
    fum_lost: "fum_lost"  // stored as negative in Sleeper
  };

  // Sleeper roster_positions tokens -> slot key.
  // FLEX covers all RB/WR/TE flex types Sleeper uses.
  function _sleeperSlots(positions) {
    var slots = { QB: 0, RB: 0, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0, K: 0, DST: 0, BN: 0 };
    var FLEX_TOKENS = ["FLEX", "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX", "RBTE_FLEX"];
    (positions || []).forEach(function (p) {
      if (p === "QB") slots.QB++;
      else if (p === "RB") slots.RB++;
      else if (p === "WR") slots.WR++;
      else if (p === "TE") slots.TE++;
      else if (FLEX_TOKENS.indexOf(p) >= 0) slots.FLEX++;
      else if (p === "SUPER_FLEX") slots.SUPERFLEX++;
      else if (p === "K") slots.K++;
      else if (p === "DEF") slots.DST++;
      else if (p === "BN") slots.BN++;
      // IR ignored per spec
    });
    return slots;
  }

  // Convert Sleeper API responses to the league shape.
  // lg: /v1/league/<id>; users: /v1/league/<id>/users;
  // drafts: /v1/league/<id>/drafts
  function fromSleeper(lg, users, drafts) {
    if (!lg) lg = {};
    var sc = lg.scoring_settings || {};
    var settings = lg.settings || {};

    // Scoring
    var scoring = {};
    Object.keys(SLEEPER_SCORING).forEach(function (k) {
      var engineKey = SLEEPER_SCORING[k];
      var v = sc[k];
      scoring[engineKey] = (typeof v === "number" && isFinite(v)) ? v : DEFAULT_SCORING[engineKey];
    });

    // Slots
    var slots = _sleeperSlots(lg.roster_positions);

    // Budget from drafts[0].settings.budget if present, else 200
    var budget = 200;
    var draftArr = Array.isArray(drafts) ? drafts : [];
    if (draftArr.length > 0) {
      var draftBudget = draftArr[0].settings && Number(draftArr[0].settings.budget);
      if (isFinite(draftBudget) && draftBudget > 0) budget = draftBudget;
    }

    // Teams from users array; team name: metadata.team_name or display_name
    var teams = (Array.isArray(users) ? users : []).map(function (u) {
      var md = u.metadata || {};
      var name = (typeof md.team_name === "string" && md.team_name.trim()) || u.display_name || "Team";
      return { name: name.trim(), budget: budget };
    });

    // If no users, build N empty team slots from total_rosters
    if (!teams.length) {
      var n = Number(settings.num_teams || lg.total_rosters) || 0;
      for (var i = 0; i < n; i++) teams.push({ name: "Team " + (i + 1), budget: budget });
    }

    var recVal = typeof sc.rec === "number" ? sc.rec : 0;
    var scoringLabel = recVal >= 1 ? "PPR" : recVal >= 0.5 ? "Half PPR" : "Standard";
    if (_isCustomScoring(scoring, recVal)) scoringLabel = "Custom";

    return {
      platform: "sleeper",
      leagueId: String(lg.league_id || ""),
      name: lg.name || "",
      teams: teams,
      budget: budget,
      minBid: 1,
      slots: slots,
      scoring: scoring,
      scoringLabel: scoringLabel,
      notes: []
    };
  }

  // ---- fromEspn -------------------------------------------------------

  // ESPN lineup slot IDs -> league slot keys.
  var ESPN_SLOTS = {
    "0":  "QB",
    "2":  "RB",
    "4":  "WR",
    "6":  "TE",
    "7":  "SUPERFLEX",  // OP = Offensive Player (all skill positions)
    "16": "DST",
    "17": "K",
    "20": "BN",
    "23": "FLEX",       // W/R/T flex
    "24": "FLEX",       // W/T flex (also counts toward FLEX)
    "25": "FLEX"        // W/R/T variant
  };

  // ESPN stat IDs -> engine scoring keys.
  // isReversal: true means the stat's points subtract (penalty).
  var ESPN_STAT = {
    3:  "pass_yds",
    4:  "pass_tds",
    20: "ints",       // INTs thrown; isReversal flips sign
    24: "rush_yds",
    25: "rush_tds",
    42: "rec",
    53: "rec_yds",
    43: "rec_tds",
    72: "fum_lost"    // fumbles lost; isReversal flips sign
  };

  // Convert ESPN API mSettings+mTeam response to the league shape.
  function fromEspn(json) {
    if (!json) json = {};
    var settings  = json.settings || {};
    var draftS    = settings.draftSettings || {};
    var rosterS   = settings.rosterSettings || {};
    var scoringS  = settings.scoringSettings || {};
    var slotCounts = rosterS.lineupSlotCounts || {};

    // Budget
    var budget = Number(draftS.auctionBudget) || 200;

    // Slots
    var slots = { QB: 0, RB: 0, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0, K: 0, DST: 0, BN: 0 };
    Object.keys(slotCounts).forEach(function (k) {
      var key = ESPN_SLOTS[k];
      if (key && slots[key] !== undefined) slots[key] += Number(slotCounts[k]) || 0;
    });

    // Scoring
    var scoring = {};
    Object.keys(DEFAULT_SCORING).forEach(function (k) { scoring[k] = DEFAULT_SCORING[k]; });
    (scoringS.scoringItems || []).forEach(function (item) {
      var engineKey = ESPN_STAT[item.statId];
      if (!engineKey) return;
      var pts = Number(item.points);
      if (!isFinite(pts)) return;
      // isReversal: true means the event subtracts; negate the value.
      scoring[engineKey] = item.isReversal ? -pts : pts;
    });

    // Teams
    var teams = (Array.isArray(json.teams) ? json.teams : []).map(function (t) {
      var name = ((t.location || "") + " " + (t.nickname || "")).trim() || t.abbrev || "Team";
      return { name: name, budget: budget };
    });

    var recVal = scoring.rec;
    var scoringLabel = recVal >= 1 ? "PPR" : recVal >= 0.5 ? "Half PPR" : "Standard";
    if (_isCustomScoring(scoring, recVal)) scoringLabel = "Custom";

    return {
      platform: "espn",
      leagueId: json.id !== undefined ? String(json.id) : null,
      name: settings.name || "",
      teams: teams,
      budget: budget,
      minBid: 1,
      slots: slots,
      scoring: scoring,
      scoringLabel: scoringLabel,
      notes: []
    };
  }

  // ---- parsePaste -----------------------------------------------------

  // Detect platform from paste content and dispatch to the right reader.
  // opts.rows: player rows [{player_key, name, pos, team}] for the rosters-page
  // reader (a rosters page is read only when no settings page is found).
  function parsePaste(text, opts) {
    var t = String(text || "");
    var none = { ok: false, platform: null, league: null, found: [], missing: [], unread: [] };
    if (!t.trim()) return none;

    var platform = _detectPlatform(t);
    var res = platform === "espn" ? _parseEspnPaste(t)
      : platform === "yahoo" ? _parseYahooPaste(t)
      : platform === "sleeper" ? _parseSleeperPaste(t) : null;
    if (res && res.ok) return res;
    return _parseRostersPaste(t, opts && opts.rows) || res || none;
  }

  // The live site's league reader (app/next/league-paste.js over
  // app/v2/roster-paste.js and app/next/rosterparse.js), or null.
  function _leagueReader() {
    if (root.DDF && root.DDF.leaguePaste && root.DDFRosterPaste) return root.DDF.leaguePaste;
    if (typeof require !== "function" || typeof module === "undefined") return null;
    try {
      if (!root.window) root.window = root; // rosterparse.js attaches to window
      root.DDFRosterPaste = root.DDFRosterPaste || require("../v2/roster-paste.js");
      require("../next/rosterparse.js");
      return require("../next/league-paste.js");
    } catch (e) { return null; }
  }

  // A league rosters page instead of a settings page: the live reader gives
  // the team names and the roster slots the page shows on every team.
  // Scoring and budget are not on a rosters page, so they keep the defaults
  // and are listed as missing. A slot the reader could not settle (teams
  // show different counts) is listed as missing too, never guessed.
  function _parseRostersPaste(text, rows) {
    var reader = _leagueReader();
    if (!reader || !rows || !rows.length) return null;
    var read = reader.read(text, rows);
    if (!read || !read.ok || !read.teams || read.teams.length < 2) return null;
    var inferred = (read.pasteSettings && read.pasteSettings.roster) || {};
    var slots = {}, found = ["teams (" + read.teams.length + ")", "team names"], missing = [];
    ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST", "BN"].forEach(function (k) {
      var v = inferred[k === "BN" ? "BENCH" : k];
      if (v === null || v === undefined) { missing.push("slots." + k); return; }
      slots[k] = v; found.push(v + " " + k);
    });
    var site = ["espn", "yahoo", "sleeper"].indexOf(read.site) !== -1 ? read.site : "manual";
    var out = _buildPasteResult(site, slots, {}, null, 1, read.teams.length, (read.league && read.league.leagueName) || "",
      found, missing, [], []);
    out.league.teams = read.teams.map(function (t, i) { return { name: t.name || "Team " + (i + 1), budget: out.league.budget }; });
    out.missing = out.missing.filter(function (m) { return m.indexOf("scoring.") !== 0; }).concat(["scoring"]);
    out.ok = true;
    out.source = "rosters";
    return out;
  }

  function _detectPlatform(text) {
    var lower = text.toLowerCase();
    // ESPN: "passing yards (py)" or "defense/special teams" or "scoring type" (ESPN-only label)
    if (/passing yards.*\bpy\b|rushing yards.*\bry\b|defense\/special teams|scoring type/i.test(text)) return "espn";
    // ESPN: "interceptions thrown" or "passing touchdowns (ptd)" label patterns
    if (/interceptions thrown|passing touchdowns.*ptd/i.test(text)) return "espn";
    // Sleeper: "Auction (Linear)" is Sleeper-specific draft-type label
    if (/auction \(linear\)/i.test(text)) return "sleeper";
    // Sleeper: SUPER_FLEX in roster positions (Sleeper uses underscore; Yahoo uses W/R/T)
    if (/SUPER_FLEX/.test(text)) return "sleeper";
    // Yahoo: "salary cap" or W/R/T roster format
    if (/salary cap/i.test(text)) return "yahoo";
    if (/W\/R\/T/.test(text) && /roster positions/i.test(text)) return "yahoo";
    // "Scoring" section with PPR label: check for Sleeper-specific scoring labels first
    if (/full point per reception|1\.0 ppr/i.test(text)) return "sleeper";
    if (/^scoring$/im.test(text) && /ppr|half point|half-point/i.test(text)) return "yahoo";
    return null;
  }

  // ---- ESPN paste parser -----------------------------------------------

  function _parseEspnPaste(text) {
    var lines = text.split(/\n/);
    var found = [], missing = [], unread = [], notes = [];
    var slots = {};
    var scoring = {};
    var budget = null, teams = null, leagueName = null;
    var minBid = 1;

    // Normalize: trim and collapse multiple spaces/tabs
    function norm(s) { return String(s).replace(/\t/g, "  ").replace(/  +/g, " ").trim(); }

    // Extract value from "Label\tValue" or "Label  Value" pairs
    function tabPair(line) {
      var parts = line.split(/\t/);
      if (parts.length >= 2) return { label: parts[0].trim(), val: parts[parts.length - 1].trim() };
      return null;
    }

    for (var i = 0; i < lines.length; i++) {
      var line = norm(lines[i]);
      if (!line) continue;

      // League name
      if (/^league name$/i.test(line) && i + 1 < lines.length) {
        var nextLine = norm(lines[i + 1]);
        if (nextLine && !/^(teams|scoring|draft)/i.test(nextLine)) {
          leagueName = nextLine; found.push("name"); i++;
          continue;
        }
      }
      var kv = tabPair(line);
      if (kv && /^league name$/i.test(kv.label)) {
        leagueName = kv.val; found.push("name"); continue;
      }

      // Teams count
      if (kv && /^teams$/i.test(kv.label) && /^\d+$/.test(kv.val)) {
        teams = Number(kv.val); found.push("teams"); continue;
      }

      // Auction budget
      if (kv && /^auction budget$/i.test(kv.label)) {
        var bd = Number(String(kv.val).replace(/[$,\s]/g, ""));
        if (isFinite(bd) && bd > 0) { budget = bd; found.push("budget"); }
        continue;
      }

      // Roster positions (sequential "Position (CODE)\tCount" pairs)
      var rosterM = /^(Quarterback|Running Back|Wide Receiver|Tight End|Flex \(W\/R\/T\)|Bench|Kicker|Defense\/Special Teams)\s*(?:\([A-Z/]+\))?\s*([\t ]+(\d+))?$/i.exec(line);
      if (!rosterM) {
        rosterM = line.match(/^(Quarterback|Running Back|Wide Receiver|Tight End|Flex|Kicker|Defense\/Special Teams)[^\t]*\t(\d+)/i);
      }
      if (!rosterM) {
        // Handle "Position (CODE)  N" after tab
        var kv2 = tabPair(line);
        if (kv2) {
          var slotM = kv2.label.match(/^(Quarterback|Running Back|Wide Receiver|Tight End|Flex \(W\/R\/T\)|Bench|Kicker|Defense\/Special Teams)/i);
          if (slotM && /^\d+$/.test(kv2.val)) {
            rosterM = { 1: kv2.label, 2: kv2.val };
          }
        }
      }
      if (rosterM) {
        var slotName = rosterM[1] || (rosterM[0] && rosterM[0].split(/[\t ]/)[0]) || "";
        var slotCount = Number(rosterM[2] || (kv && kv.val) || "0");
        if (!isFinite(slotCount)) continue;
        var slotKey = _espnSlotName(slotName);
        if (slotKey) { slots[slotKey] = (slots[slotKey] || 0) + slotCount; found.push("slot." + slotKey); }
        continue;
      }

      // Scoring lines: "Passing Yards (PY)\t0.04 pts" or "Passing Yards (PY)  0.04 pts"
      var scoreM = line.match(/^(.+?)\s+(-?\d+\.?\d*)\s+pts?$/i);
      if (!scoreM && kv) {
        var ptVal = kv.val.replace(/\s*pts?$/i, "").trim();
        if (/^-?\d+\.?\d*$/.test(ptVal)) {
          scoreM = { 1: kv.label, 2: ptVal };
        }
      }
      if (scoreM) {
        var statLabel = scoreM[1].replace(/\s*\([^)]+\)$/, "").trim();
        var statVal   = Number(scoreM[2]);
        var engineKey = _espnStatLabel(statLabel);
        if (engineKey) {
          scoring[engineKey] = statVal; found.push("scoring." + engineKey);
        } else if (!_isKnownIgnoredStat(statLabel)) {
          unread.push(line);
        }
        continue;
      }

      // Known unread patterns: TE premium, bonuses, 2pt conversions, etc.
      if (/te premium|bonus|2-?point|touchback|sack|safety|block/i.test(line)) {
        notes.push(line);
        unread.push(line);
      }
    }

    return _buildPasteResult("espn", slots, scoring, budget, minBid, teams, leagueName, found, missing, unread, notes);
  }

  function _espnSlotName(label) {
    var l = label.toLowerCase();
    if (/quarterback/i.test(l))    return "QB";
    if (/running back/i.test(l))   return "RB";
    if (/wide receiver/i.test(l))  return "WR";
    if (/tight end/i.test(l))      return "TE";
    if (/flex/i.test(l))           return "FLEX";
    if (/bench/i.test(l))          return "BN";
    if (/kicker/i.test(l))         return "K";
    if (/defense|d\/st/i.test(l))  return "DST";
    return null;
  }

  function _espnStatLabel(label) {
    var l = label.toLowerCase().replace(/[^a-z]/g, " ").replace(/  +/g, " ").trim();
    if (/passing yards/.test(l))           return "pass_yds";
    if (/passing touchdowns/.test(l))      return "pass_tds";
    if (/interceptions thrown/.test(l))    return "ints";
    if (/rushing yards/.test(l))           return "rush_yds";
    if (/rushing touchdowns/.test(l))      return "rush_tds";
    if (/^receptions$/.test(l))            return "rec";
    if (/receiving yards/.test(l))         return "rec_yds";
    if (/receiving touchdowns/.test(l))    return "rec_tds";
    if (/fumbles lost/.test(l))            return "fum_lost";
    return null;
  }

  function _isKnownIgnoredStat(label) {
    // Stats we know exist on ESPN but are not engine keys; skip silently.
    return /2-?point|extra point|field goal|punt|kickoff|return|tackle|sack|interception return|safety|blocked/i.test(label);
  }

  // ---- Yahoo paste parser ----------------------------------------------

  function _parseYahooPaste(text) {
    var lines = text.split(/\n/);
    var found = [], missing = [], unread = [], notes = [];
    var slots = {}, scoring = {};
    var budget = null, teams = null, leagueName = null;
    var minBid = 1;

    function norm(s) { return String(s).replace(/\t/g, "  ").replace(/  +/g, " ").trim(); }

    for (var i = 0; i < lines.length; i++) {
      var line = norm(lines[i]);
      if (!line) continue;

      // League name follows a "League Name" header
      if (/^league name$/i.test(line) && i + 1 < lines.length) {
        var val = norm(lines[i + 1]);
        if (val && !/^(privacy|scoring|draft|number|roster|teams|salary|starting)/i.test(val)) {
          leagueName = val; found.push("name"); i++; continue;
        }
      }

      // Team count: "10 Teams" or "Number of Teams" followed by "10"
      var teamsM = line.match(/^(\d+)\s+teams?$/i);
      if (teamsM) { teams = Number(teamsM[1]); found.push("teams"); continue; }
      if (/^(number of teams|max teams|teams?)$/i.test(line) && i + 1 < lines.length) {
        var nxt = norm(lines[i + 1]);
        var nm = nxt.match(/^(\d+)/);
        if (nm) { teams = Number(nm[1]); found.push("teams"); i++; continue; }
      }

      // Salary cap / auction budget
      if (/^salary cap$/i.test(line) && i + 1 < lines.length) {
        var capLine = norm(lines[i + 1]);
        var capM = capLine.match(/\$?(\d+)/);
        if (capM) { budget = Number(capM[1]); found.push("budget"); i++; continue; }
      }
      var capM2 = line.match(/^(auction budget|salary cap)[:\s]+\$?(\d+)/i);
      if (capM2) { budget = Number(capM2[2]); found.push("budget"); continue; }

      // Starting bid
      if (/^starting bid$/i.test(line) && i + 1 < lines.length) {
        var bidLine = norm(lines[i + 1]);
        var bidM = bidLine.match(/\$?(\d+)/);
        if (bidM) { minBid = Number(bidM[1]); found.push("minBid"); i++; continue; }
      }

      // Roster positions: "QB, WR, WR, RB, ..."
      if (/^roster positions$/i.test(line) && i + 1 < lines.length) {
        var rp = norm(lines[i + 1]);
        if (/^[QRWTKDEFBNa-z,/ ]+$/i.test(rp) && /,/.test(rp)) {
          _parseYahooRosterLine(rp, slots, found);
          i++; continue;
        }
      }
      // Inline: "Roster Positions: QB, WR, ..."
      var rpM = line.match(/^roster positions[:\s]+([QRWTKDEFBNa-z,/ ]+)$/i);
      if (rpM) { _parseYahooRosterLine(rpM[1], slots, found); continue; }

      // Scoring lines
      var scoreKey = _yahooStatLine(line);
      if (scoreKey) {
        // Value on the same line or next line
        var scoreVal = _extractNum(line);
        if (scoreVal === null && i + 1 < lines.length) {
          scoreVal = _extractNum(norm(lines[i + 1]));
          if (scoreVal !== null) i++;
        }
        if (scoreVal !== null) {
          scoring[scoreKey] = scoreVal; found.push("scoring." + scoreKey);
        }
        continue;
      }

      if (/te premium|bonus|2-?point|touchback|return/i.test(line)) {
        notes.push(line); unread.push(line);
      }
    }

    return _buildPasteResult("yahoo", slots, scoring, budget, minBid, teams, leagueName, found, missing, unread, notes);
  }

  function _parseYahooRosterLine(rp, slots, found) {
    var tokens = rp.toUpperCase().split(/[\s,]+/).filter(Boolean);
    var slotMap = { QB: 0, RB: 0, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0, K: 0, DST: 0, BN: 0 };
    tokens.forEach(function (tok) {
      if (tok === "QB")           slotMap.QB++;
      else if (tok === "RB")      slotMap.RB++;
      else if (tok === "WR")      slotMap.WR++;
      else if (tok === "TE")      slotMap.TE++;
      else if (tok === "W/R/T" || tok === "W/R" || tok === "FLEX") slotMap.FLEX++;
      else if (tok === "K")       slotMap.K++;
      else if (tok === "DEF" || tok === "D/ST" || tok === "DST") slotMap.DST++;
      else if (tok === "BN")      slotMap.BN++;
    });
    Object.keys(slotMap).forEach(function (k) { slots[k] = slotMap[k]; });
    found.push("slots");
  }

  function _yahooStatLine(line) {
    var l = line.toLowerCase().replace(/[^a-z]/g, " ").replace(/  +/g, " ").trim();
    if (/passing yards/.test(l))       return "pass_yds";
    if (/passing touchdowns/.test(l))  return "pass_tds";
    if (/interceptions?$/.test(l) || /^interceptions?$/.test(l)) return "ints";
    if (/rushing yards/.test(l))       return "rush_yds";
    if (/rushing touchdowns/.test(l))  return "rush_tds";
    if (/^receptions?$/.test(l))       return "rec";
    if (/receiving yards/.test(l))     return "rec_yds";
    if (/receiving touchdowns/.test(l)) return "rec_tds";
    if (/fumbles lost/.test(l))        return "fum_lost";
    return null;
  }

  function _extractNum(line) {
    var m = line.match(/(-?\d+\.?\d*)/);
    if (!m) return null;
    var v = Number(m[1]);
    return isFinite(v) ? v : null;
  }

  // ---- Sleeper paste parser -------------------------------------------

  function _parseSleeperPaste(text) {
    // Sleeper paste follows a similar pattern to Yahoo: label then value.
    var lines = text.split(/\n/);
    var found = [], missing = [], unread = [], notes = [];
    var slots = {}, scoring = {};
    var budget = null, teams = null, leagueName = null;
    var minBid = 1;

    function norm(s) { return String(s).replace(/\t/g, "  ").replace(/  +/g, " ").trim(); }

    for (var i = 0; i < lines.length; i++) {
      var line = norm(lines[i]);
      if (!line) continue;

      if (/^league name$/i.test(line) && i + 1 < lines.length) {
        var val = norm(lines[i + 1]);
        if (val && !/^(league size|draft|scoring|auction|roster)/i.test(val)) {
          leagueName = val; found.push("name"); i++; continue;
        }
      }

      var teamsM = line.match(/^(\d+)\s+teams?$/i);
      if (teamsM) { teams = Number(teamsM[1]); found.push("teams"); continue; }
      if (/^league size$/i.test(line) && i + 1 < lines.length) {
        var nxt = norm(lines[i + 1]);
        var nm = nxt.match(/^(\d+)/);
        if (nm) { teams = Number(nm[1]); found.push("teams"); i++; continue; }
      }

      var capM2 = line.match(/^(auction budget)[:\s]+\$?(\d+)/i);
      if (capM2) { budget = Number(capM2[2]); found.push("budget"); continue; }
      if (/^(auction budget|\$\d+)$/i.test(line) && i + 1 < lines.length) {
        var budLine = norm(lines[i + 1]);
        var budM = budLine.match(/\$?(\d+)/);
        if (budM) { budget = Number(budM[1]); found.push("budget"); i++; continue; }
      }
      // "$200" on a line by itself after auction heading
      if (/^\$(\d+)$/.test(line)) {
        var prev = i > 0 ? norm(lines[i - 1]) : "";
        if (/auction/i.test(prev)) { budget = Number(line.slice(1)); found.push("budget"); continue; }
      }

      // Roster positions line
      var rpM = line.match(/^roster positions[:\s]+([QRWTKDEFBNa-z,/ ]+)$/i);
      if (rpM) { _parseSleeperRosterLine(rpM[1], slots, found); continue; }
      if (/^roster positions$/i.test(line) && i + 1 < lines.length) {
        var rp = norm(lines[i + 1]);
        if (/QB/i.test(rp) && /,/.test(rp)) {
          _parseSleeperRosterLine(rp, slots, found); i++; continue;
        }
      }

      var scoreKey = _yahooStatLine(line); // Sleeper paste uses similar labels
      if (scoreKey) {
        var scoreVal = _extractNum(line);
        if (scoreVal === null && i + 1 < lines.length) {
          scoreVal = _extractNum(norm(lines[i + 1]));
          if (scoreVal !== null) i++;
        }
        if (scoreVal !== null) {
          scoring[scoreKey] = scoreVal; found.push("scoring." + scoreKey);
        }
        continue;
      }

      if (/te premium|bonus|2-?point|touchback|return/i.test(line)) {
        notes.push(line); unread.push(line);
      }
    }

    return _buildPasteResult("sleeper", slots, scoring, budget, minBid, teams, leagueName, found, missing, unread, notes);
  }

  function _parseSleeperRosterLine(rp, slots, found) {
    // Sleeper positions may include SUPER_FLEX, BN tokens
    var FLEX_TOKENS = ["FLEX", "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX", "RBTE_FLEX"];
    var tokens = rp.toUpperCase().split(/[\s,]+/).filter(Boolean);
    var slotMap = { QB: 0, RB: 0, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0, K: 0, DST: 0, BN: 0 };
    tokens.forEach(function (tok) {
      if (tok === "QB")           slotMap.QB++;
      else if (tok === "RB")      slotMap.RB++;
      else if (tok === "WR")      slotMap.WR++;
      else if (tok === "TE")      slotMap.TE++;
      else if (FLEX_TOKENS.indexOf(tok) >= 0) slotMap.FLEX++;
      else if (tok === "SUPER_FLEX") slotMap.SUPERFLEX++;
      else if (tok === "K")          slotMap.K++;
      else if (tok === "DEF" || tok === "D/ST" || tok === "DST") slotMap.DST++;
      else if (tok === "BN")         slotMap.BN++;
    });
    Object.keys(slotMap).forEach(function (k) { slots[k] = slotMap[k]; });
    found.push("slots");
  }

  // ---- shared paste helpers -------------------------------------------

  // Build the final parsePaste result, applying defaults for missing fields.
  function _buildPasteResult(platform, slots, scoring, budget, minBid, teams, leagueName, found, missing, unread, notes) {
    var slotsMissing = !Object.keys(slots).some(function (k) { return slots[k] > 0; });
    var finalSlots = slotsMissing ? Object.assign({}, DEFAULT_SLOTS) : _mergeSlots(slots);
    if (slotsMissing) missing.push("slots");

    var finalScoring = {};
    Object.keys(DEFAULT_SCORING).forEach(function (k) {
      if (scoring[k] !== undefined) {
        finalScoring[k] = scoring[k];
      } else {
        finalScoring[k] = DEFAULT_SCORING[k];
        if (found.indexOf("scoring." + k) < 0) missing.push("scoring." + k);
      }
    });

    var finalBudget = budget !== null ? budget : 200;
    if (budget === null) missing.push("budget");

    var finalMinBid = minBid || 1;
    var n = teams || 0;
    var teamList = [];
    for (var i = 0; i < n; i++) teamList.push({ name: "Team " + (i + 1), budget: finalBudget });

    var recVal = finalScoring.rec;
    var scoringLabel = recVal >= 1 ? "PPR" : recVal >= 0.5 ? "Half PPR" : "Standard";
    if (_isCustomScoring(finalScoring, recVal)) scoringLabel = "Custom";

    var league = {
      platform: platform,
      leagueId: null,
      name: leagueName || "",
      teams: teamList,
      budget: finalBudget,
      minBid: finalMinBid,
      slots: finalSlots,
      scoring: finalScoring,
      scoringLabel: scoringLabel,
      notes: notes
    };

    var ok = !slotsMissing || Object.keys(scoring).length > 0 || budget !== null;

    return { ok: ok, platform: platform, league: league, found: found, missing: missing, unread: unread };
  }

  function _mergeSlots(partial) {
    var out = {};
    var KEYS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DST", "BN"];
    KEYS.forEach(function (k) { out[k] = (partial[k] !== undefined ? partial[k] : DEFAULT_SLOTS[k]) || 0; });
    return out;
  }

  // Returns true when scoring differs from all three standard profiles.
  function _isCustomScoring(scoring, recVal) {
    var base = {
      pass_yds: 0.04, pass_tds: 4, rush_yds: 0.1, rush_tds: 6,
      rec_yds: 0.1, rec_tds: 6
    };
    for (var k in base) {
      if (scoring[k] !== undefined && scoring[k] !== base[k]) return true;
    }
    // fum_lost: -2 is universal default; ints: -2 for ESPN/Sleeper, -1 for Yahoo default
    return false;
  }

  // ---- exports --------------------------------------------------------

  var DraftLeague = {
    parseRef: parseRef,
    settingsUrl: settingsUrl,
    load: load,
    fromSleeper: fromSleeper,
    fromEspn: fromEspn,
    parsePaste: parsePaste
  };

  root.DraftLeague = DraftLeague;
  if (typeof module !== "undefined" && module.exports) module.exports = DraftLeague;
})(typeof globalThis !== "undefined" ? globalThis : this);
