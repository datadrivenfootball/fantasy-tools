/* DDF staging: league bridge for the live pages (JEG-1736; team.html, find.html, build.html).
 *
 * The staging page is a small shell:
 *   <script src="(supabase umd)"></script><script src="weekly.js"></script>
 *   <script src="league-bridge.js" data-live-page="team.html" data-add="team-cover.css,team-cover.js"></script>
 *
 * What it does, in order:
 *   1. Reads the sign-in session (this tab's sessionStorage, as app.js), then GET /leagues/:id and /leagues/:id/weekly.
 *   2. Fetches the DEPLOYED live page. The file in app/next is not enough: the site build embeds the value engine and
 *      the player data in the page, so the page is taken as published, never copied into this repo.
 *   3. Reads the stored rosters with the live matcher (DDF.leaguePaste.fromBlocks, the reader a paste uses) on the
 *      page's own player rows, and writes the ddf:pasted record the live pages read. sessionStorage only: this origin
 *      is shared with the live site, so nothing here touches localStorage.
 *   4. Writes the live page into this document unchanged, plus: a <base> to the live site (every relative script,
 *      data file and link keeps working), noindex, and one deferred call placed just before ddf-league.js that applies
 *      the league's settings for this visit (DDF.engine.applyVisit, nothing saved) before the page reads the league.
 *   5. After the page has its league: the staging tag, staging nav links, then the page's own additions (data-add).
 *
 * window.DDFStaging = {ready: Promise<{league, summary, weekly}>, league, summary, weekly, weeklyError, me,
 *   matched: {teams: [{team_key, name, players: [{key, player_id}], unmatched: [{player_id, name}]}]},
 *   mock: bool (?mock=1 on localhost; panels may show sample data), url(name) -> absolute staging URL}
 * and a "ddf-staging:ready" event on document. */
(function () {
  "use strict";
  var LIVE = "https://datadrivenfootball.github.io/fantasy-tools/";
  var SUPABASE_URL = "https://iskiybsimubiujwuchsl.supabase.co";
  var PUBLISHABLE_KEY = "sb_publishable_pzHxlyPf-jZFpStnejUUsQ_OaYuj4j7"; /* public by design */
  var FN = window.DDF_STAGING_FN || SUPABASE_URL + "/functions/v1/ddf-account"; /* override only in the local test harness */
  var tag = document.currentScript, cfg = (tag && tag.dataset) || {};
  var HERE = new URL(".", location.href).href; /* the staging folder */
  var QS = new URLSearchParams(location.search);
  var IS_LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  var list = function (s) { return String(s || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean); };
  var LIVE_PAGE = cfg.livePage || "team.html", ADD = list(cfg.add), STAGING_PAGES = list(cfg.stagingPages || "team.html,find.html,build.html");
  var sb = null, resolveReady;
  var S = window.DDFStaging = {league: null, summary: null, weekly: null, weeklyError: null, me: null, matched: {teams: []},
    mock: IS_LOCAL && QS.get("mock") === "1", url: function (name) { return new URL(name, HERE).href; }};
  S.ready = new Promise(function (r) { resolveReady = r; });

  function say(text, link) {
    var box = document.getElementById("bridge-status");
    if (!box) return;
    box.textContent = text + " ";
    if (link) { var a = document.createElement("a"); a.href = S.url("./"); a.textContent = "Add your league"; box.appendChild(a); box.appendChild(document.createTextNode(".")); }
  }
  async function api(path) {
    var s = (await sb.auth.getSession()).data.session;
    if (!s) throw new Error("Sign in first.");
    var r = await fetch(FN + path, {headers: {authorization: "Bearer " + s.access_token, apikey: PUBLISHABLE_KEY, "content-type": "application/json"}});
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error((j.error && j.error.message) || "Something went wrong on our side. Try again in a minute.");
    return j;
  }
  function loadScript(src) {
    return new Promise(function (ok, bad) {
      var s = document.createElement("script");
      s.src = src; s.async = false; s.onload = ok; s.onerror = function () { bad(new Error("Could not load " + src)); };
      document.head.appendChild(s);
    });
  }

  /* ---------- the stored league as the record the live pages read ---------- */
  function lineOf(p) { return [p.name, p.position, p.nfl_team].filter(Boolean).join(" "); }
  function buildRecord(league, summary, rows) {
    var teams = summary.teams || [];
    var blocks = teams.map(function (t) { return {name: t.name, text: (t.roster || []).filter(function (p) { return p && p.name; }).map(lineOf).join("\n")}; });
    var res = window.DDF.leaguePaste.fromBlocks(blocks, rows, {site: summary.platform || "unknown", strategy: "ddf-account"});
    var rec = window.DDF.leaguePaste.record(res, summary.platform || "paste");
    var me = teams.map(function (t) { return t.team_key; }).indexOf(league.my_team_key);
    rec.name = league.name || summary.name || "Your league";
    if (me >= 0) { rec.me = me; rec.own = me; }
    rec.staging = {league_id: league.id, pulled_at: summary.pulled_at || null};
    /* engine key -> stored player_id, team by team (same order as the record's teams) */
    S.matched = {teams: teams.map(function (t, i) {
      var byLine = {}, used = {};
      (t.roster || []).forEach(function (p) { if (p && p.name) byLine[lineOf(p).trim().slice(0, 80)] = p; });
      var players = ((res.teams[i] || {}).players || []).map(function (p) {
        var src = byLine[p.line] || (t.roster || []).filter(function (x) { return x.name === p.name; })[0] || null;
        if (src) used[src.player_id] = true;
        return {key: p.key, player_id: src ? src.player_id : null};
      });
      return {team_key: t.team_key, name: t.name, players: players,
        unmatched: (t.roster || []).filter(function (p) { return p && !used[p.player_id]; }).map(function (p) { return {player_id: p.player_id, name: p.name}; })};
    })};
    S.me = me >= 0 ? me : null;
    return rec;
  }
  function settingsOf(league, summary) {
    var d = league.confirmed_settings || (summary.settings && summary.settings.ddf);
    if (!d || !d.scoring) return null;
    var out = {scoring: d.scoring, superflex: !!d.superflex};
    if (d.teams) out.teams = d.teams;
    if (d.superflexSlots) out.superflexSlots = d.superflexSlots;
    if (d.roster) out.roster = d.roster;
    return out;
  }

  /* ---------- the live page, written into this document ---------- */
  function patchPage(html) {
    var head = '<base href="' + LIVE + '"><meta name="robots" content="noindex, nofollow">';
    html = html.replace(/<head([^>]*)>/i, function (m) { return m + head; });
    html = html.replace(/<title>([^<]*)<\/title>/i, function (m, t) { return "<title>" + t + " (staging)</title>"; });
    /* Deferred scripts run in page order, so this one runs after ddf-engine.js and before ddf-league.js. */
    var hook = '<script defer src="data:text/javascript,window.DDFStaging._engine()"></script>';
    var at = html.search(/<script\b[^>]*\bsrc="ddf-league\.js/i);
    return at >= 0 ? html.slice(0, at) + hook + html.slice(at) : html.replace(/<\/body>/i, hook + "</body>");
  }
  /* Runs once the page is parsed, before ddf-league.js: the league's settings, for this visit only. */
  S._engine = function () {
    var eng = window.DDF && window.DDF.engine, partial = S._settings;
    var applied = eng && eng.ready ? eng.ready.then(function () { if (partial && eng.applyVisit) { try { eng.applyVisit(partial); } catch (e) { console.error(e); } } }) : Promise.resolve();
    applied.catch(function () { /* the page shows its own "engine did not load" state */ }).then(function () {
      var lg = window.DDF && window.DDF.league;
      return lg && lg.ready ? lg.ready.catch(function () { return null; }) : null;
    }).then(function () {
      chrome();
      resolveReady({league: S.league, summary: S.summary, weekly: S.weekly});
      return ADD.reduce(function (p, name) {
        return p.then(function () {
          if (/\.css$/.test(name)) { var l = document.createElement("link"); l.rel = "stylesheet"; l.href = S.url(name); document.head.appendChild(l); return null; }
          return loadScript(S.url(name));
        });
      }, Promise.resolve());
    }).then(function () { document.dispatchEvent(new CustomEvent("ddf-staging:ready", {detail: {league: S.league, summary: S.summary, weekly: S.weekly}})); },
      function (e) { console.error(e); });
  };
  /* Data age (JEG-1736): the league data is a snapshot that does not refresh by itself, so every page says how old it
   * is. Attention when it is over 6 hours old, or when a game of the current week has kicked off since the pull.
   * games-left.js carries the same function (that page does not load the bridge). */
  function dataAge(summary, weekly, now) {
    var flaim = !!(summary.source && summary.source.kind === "flaim"), site = String(summary.platform || "");
    var from = "League data from " + (site ? site.charAt(0).toUpperCase() + site.slice(1) : "your league site") + (flaim ? " via Flaim" : "");
    var tail = flaim ? " It does not refresh on its own yet." : "";
    var at = Date.parse(summary.pulled_at || "");
    if (!isFinite(at)) return {text: from + ". The time it was pulled was not recorded." + tail, stale: true};
    var mins = Math.max(0, Math.floor((now - at) / 60000)), hours = Math.floor(mins / 60), days = Math.floor(hours / 24);
    var ago = mins < 1 ? "just now" : mins < 60 ? mins + (mins === 1 ? " minute ago" : " minutes ago") : hours < 48 ? hours + (hours === 1 ? " hour ago" : " hours ago") : days + " days ago";
    var local = new Date(at).toLocaleString(undefined, {weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"});
    var ko = ((weekly && weekly.kickoffs) || {})[String(summary.current_week)] || {};
    var kicked = Object.keys(ko).map(function (t) { return Date.parse(ko[t]); }).filter(function (k) { return isFinite(k) && k <= now; });
    var behind = kicked.length > 0 && at < Math.max.apply(null, kicked); /* the latest kickoff that has passed came after the pull */
    return {text: from + ", pulled " + ago + " (" + local + ")." + tail + (behind ? " Games have kicked off since, so scores and lineups here are behind." : ""), stale: behind || now - at > 6 * 3600000};
  }
  function ageStrip() {
    var main = document.querySelector("main");
    if (!main || !S.summary) return;
    var p = document.getElementById("ddf-data-age");
    if (!p) { p = document.createElement("p"); p.id = "ddf-data-age"; main.insertBefore(p, main.firstChild); }
    var a = dataAge(S.summary, S.weekly, Date.now());
    p.textContent = a.text;
    p.className = "ddf-data-age" + (a.stale ? " stale" : "");
  }
  /* Staging tag, and nav links that stay on staging (site.js redraws the nav, so this is re-applied). */
  function chrome() {
    var brand = document.querySelector("header .brand");
    if (brand && !document.querySelector(".ddf-staging-tag")) {
      var t = document.createElement("span");
      t.className = "ddf-staging-tag"; t.title = "Private test build, not the live site"; t.textContent = "staging";
      t.style.cssText = 'font:500 10px "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:#cfe3d6;border:1px solid rgba(255,255,255,.35);border-radius:99px;padding:2px 7px;white-space:nowrap';
      brand.insertAdjacentElement("afterend", t);
    }
    /* One more nav link and the tag do not fit beside the league chip on a laptop, so the nav takes its own row there. */
    if (!document.getElementById("ddf-staging-style")) {
      var st = document.createElement("style");
      st.id = "ddf-staging-style";
      st.textContent = "@media(min-width:901px) and (max-width:1500px){body:not(.home2) header .header-inner{flex-wrap:wrap;row-gap:0;padding-top:10px}body:not(.home2) header nav{order:9;flex:1 0 100%;padding:6px 0 8px;margin-left:-13px}body:not(.home2) header .ddf-staging-tag{margin-right:auto}}" +
        /* phone: no room in the row, so the tag sits under the wordmark and takes no width */
        "@media(max-width:900px){header .header-inner{position:relative}header .ddf-staging-tag{position:absolute;left:16px;bottom:1px;border:0!important;padding:0!important;font-size:8px!important;line-height:1}}" +
        /* the data-age line: fine print, and the live attention colours when the snapshot is behind */
        "main>.ddf-data-age{margin:0 0 16px;max-width:none;font-size:13px;line-height:1.45;color:var(--muted)}main>.ddf-data-age.stale{padding:8px 12px;border-left:3px solid var(--attention-text);border-radius:0 8px 8px 0;background:var(--attention);color:var(--attention-text)}";
      document.head.appendChild(st);
    }
    ageStrip();
    if (!S._ageTimer) S._ageTimer = setInterval(ageStrip, 60000); /* the relative time, and a kickoff passing, while the tab stays open */
    var nav = document.querySelector("header nav");
    if (!nav) return;
    var busy = false;
    function fix() {
      if (busy) return;
      busy = true;
      Array.prototype.forEach.call(nav.querySelectorAll("a[href]"), function (a) {
        var file = (a.getAttribute("href") || "").split(/[?#]/)[0];
        if (STAGING_PAGES.indexOf(file) >= 0) {
          var u = new URL(S.url(a.getAttribute("href")));
          if (S.league && !u.searchParams.get("league")) u.searchParams.set("league", S.league.id); // stay on this league
          a.href = u.href;
        }
      });
      // the Team link, matched by its path (its href now carries ?league=)
      Array.prototype.filter.call(nav.querySelectorAll("a[href]"), function (x) { try { return /\/team\.html$/.test(new URL(x.href, location.href).pathname); } catch (e) { return false; } }).forEach(function (team) {
        var next = team.nextElementSibling;
        if (next && next.dataset && next.dataset.staging === "games-left") return;
        var g = document.createElement("a");
        g.href = S.url("games-left.html" + (S.league ? "?league=" + encodeURIComponent(S.league.id) : "")); g.textContent = "Games left"; g.dataset.staging = "games-left";
        if (team.className) g.className = team.className;
        team.insertAdjacentElement("afterend", g);
      });
      busy = false;
    }
    fix();
    new MutationObserver(fix).observe(nav, {childList: true, subtree: true});
  }

  async function boot() {
    if (!window.supabase) throw new Error("Sign-in did not load. Check your connection and reload.");
    sb = window.supabase.createClient(SUPABASE_URL, PUBLISHABLE_KEY, {auth: {flowType: "implicit", detectSessionInUrl: true, persistSession: true, storage: window.sessionStorage}});
    if (!(await sb.auth.getSession()).data.session) { say("Sign in to see your league here.", true); return; }
    var id = QS.get("league");
    if (!id) {
      var me = await api("/me");
      var first = (me.leagues || []).filter(function (l) { return l.my_team_key; })[0];
      if (!first) { say((me.leagues || []).length ? "Pick your team in your league first." : "No league yet.", true); return; }
      id = first.id;
    }
    var path = "/leagues/" + encodeURIComponent(id);
    var got = await Promise.all([
      api(path),
      api(path + "/weekly").then(function (j) { return j.weekly || j; }, function (e) { S.weeklyError = e.message || String(e); return null; }),
      fetch(LIVE + LIVE_PAGE, {credentials: "omit"}).then(function (r) { if (!r.ok) throw new Error("The live page did not load (" + r.status + ")."); return r.text(); }),
      window.DDF && window.DDF.leaguePaste ? null : loadScript(LIVE + "rosterparse.js").then(function () { return loadScript(LIVE + "v2/roster-paste.js"); }).then(function () { return loadScript(LIVE + "league-paste.js"); })
    ]);
    var league = got[0].league, html = got[2];
    if (!league || !league.summary) throw new Error("This league has not been read yet. Open it on the Add your league page and press Refresh now.");
    if (!league.my_team_key) { say("Pick your team in this league first.", true); return; }
    var summary = Object.assign({}, league.summary, {my_team_key: league.my_team_key});
    S.league = league; S.summary = summary; S.weekly = got[1]; S._settings = settingsOf(league, summary);

    /* the page's own player rows (the rows DDF.engine gives a paste), read from the page before it runs */
    var m = /<script id="players-data"[^>]*>([\s\S]*?)<\/script>/.exec(html), rows = [];
    try { rows = (JSON.parse(m[1]).players || []).filter(function (r) { return r && r.name && r.player_key !== undefined && r.player_key !== null; })
      .map(function (r) { return {player_key: r.player_key, name: r.name, pos: r.pos || "", team: r.team || ""}; }); } catch (e) { rows = []; }
    if (!rows.length) throw new Error("The live page has no player data to match your rosters against.");
    var rec = buildRecord(league, summary, rows);
    try { sessionStorage.setItem("ddf:pasted", JSON.stringify(rec)); ["ddf:league", "ddf:link"].forEach(function (k) { sessionStorage.removeItem(k); }); }
    catch (e) { throw new Error("This browser is blocking storage for this tab, so the league cannot be shown."); }

    document.open();
    document.write(patchPage(html));
    document.close();
  }
  boot().catch(function (err) { say(err.message || String(err)); });
})();
