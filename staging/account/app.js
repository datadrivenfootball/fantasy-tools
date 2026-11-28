/* DDF staging: sign in › connect › pick league and team › confirm settings › view (JEG-1732).
 * Every platform string is written with textContent, never as HTML. */
(function () {
  "use strict";
  var SUPABASE_URL = "https://iskiybsimubiujwuchsl.supabase.co";
  var PUBLISHABLE_KEY = "sb_publishable_pzHxlyPf-jZFpStnejUUsQ_OaYuj4j7"; /* public by design */
  var FN = window.DDF_STAGING_FN || SUPABASE_URL + "/functions/v1/ddf-account"; /* override only in the local test harness */
  var HERE = location.origin + location.pathname;
  /* The session lives in this tab's sessionStorage, not localStorage: the origin is shared with the public
     site (datadrivenfootball.github.io), and other tabs on it cannot read another tab's sessionStorage. */
  var sb = window.supabase.createClient(SUPABASE_URL, PUBLISHABLE_KEY, {auth: {flowType: "implicit", detectSessionInUrl: true, persistSession: true, storage: window.sessionStorage}});
  var $ = function (id) { return document.getElementById(id); };
  var NAMES = {espn: "ESPN", yahoo: "Yahoo", sleeper: "Sleeper"};
  var state = {me: null, league: null, view: "plain"};

  function el(tag, attrs) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) { var c = arguments[i]; if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    return n;
  }
  function say(text, kind) { var m = $("msg"); m.textContent = text || ""; m.className = "msg" + (kind ? " " + kind : ""); }
  function step(name) {
    var order = ["signin", "connect", "team", "settings", "done"], at = order.indexOf(name);
    Array.prototype.forEach.call($("steps").children, function (li) {
      var i = order.indexOf(li.dataset.step);
      li.className = i < at ? "done" : "";
      if (i === at) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
  }
  function when(iso) {
    if (!iso) return "never";
    var d = new Date(iso);
    return d.toLocaleString(undefined, {month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"});
  }

  async function api(method, path, body) {
    var s = (await sb.auth.getSession()).data.session;
    if (!s) throw new Error("Sign in first.");
    var r = await fetch(FN + path, {method: method, headers: {authorization: "Bearer " + s.access_token, apikey: PUBLISHABLE_KEY, "content-type": "application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok) { var err = new Error((j.error && j.error.message) || "Something went wrong on our side. Try again in a minute."); err.code = (j.error && j.error.code) || ""; throw err; }
    return j;
  }
  function busy(btn, fn) {
    return async function (e) {
      if (e) e.preventDefault();
      var b = btn || (e && e.submitter);
      if (b) b.disabled = true;
      try { await fn(e); } catch (err) { say(err.message || String(err), "err"); } finally { if (b) b.disabled = false; }
    };
  }

  /* ---------- sign in ---------- */
  $("email-form").addEventListener("submit", busy(null, async function () {
    var email = $("email").value.trim();
    /* In the DDF app the emailed link opens the app (ddf://signin), which hands the sign-in to this page. */
    var res = await sb.auth.signInWithOtp({email: email, options: {emailRedirectTo: IS_APP ? "ddf://signin" : HERE}});
    if (res.error) throw new Error(res.error.message);
    say("Check your email for the sign-in link. It works once and expires in an hour.", "ok");
  }));
  $("google").addEventListener("click", busy($("google"), async function () {
    var res = await sb.auth.signInWithOAuth({provider: "google", options: {redirectTo: HERE}});
    if (res.error) throw new Error(res.error.message.indexOf("not enabled") >= 0 ? "Google sign-in is not switched on yet." : res.error.message);
  }));
  $("signout").addEventListener("click", busy($("signout"), async function () { await sb.auth.signOut(); location.hash = ""; render(); }));

  /* ---------- connect ---------- */
  $("sleeper-form").addEventListener("submit", busy(null, async function () {
    var j = await api("POST", "/sleeper/connect", {username: $("sleeper-user").value.trim()});
    say("Connected Sleeper as " + j.connection.display_name + ".", "ok");
    showOptions(j.connection, j.leagues);
    await loadMe();
  }));
  /* provider toggle: the site's ESPN / Yahoo / Sleeper switch shows one panel; the selected pill slides
     the way connect.html's does (.pill-slide, styled by connect-page.css) */
  var toggle = document.querySelector(".provider-toggle"), pill = el("span", {class: "pill-slide", "aria-hidden": "true"});
  toggle.style.position = "relative"; toggle.insertBefore(pill, toggle.firstChild);
  function placePill() {
    var on = toggle.querySelector('[aria-pressed="true"]');
    if (!on || !on.offsetWidth) return;
    pill.style.width = on.offsetWidth + "px"; pill.style.transform = "translateX(" + on.offsetLeft + "px)";
    requestAnimationFrame(function () { pill.classList.add("ready"); });
  }
  window.addEventListener("resize", placePill);
  Array.prototype.forEach.call(document.querySelectorAll("[data-provider]"), function (b) {
    b.addEventListener("click", function () {
      Array.prototype.forEach.call(document.querySelectorAll("[data-provider]"), function (x) { var on = x === b; x.setAttribute("aria-pressed", String(on)); x.classList.toggle("selected", on); });
      Array.prototype.forEach.call(document.querySelectorAll("[data-panel]"), function (pn) { pn.hidden = pn.dataset.panel !== b.dataset.provider; });
      placePill();
    });
  });
  /* segmented settings controls */
  Array.prototype.forEach.call(document.querySelectorAll("[data-seg] button"), function (b) {
    b.addEventListener("click", function () { Array.prototype.forEach.call(b.parentNode.children, function (x) { x.setAttribute("aria-pressed", String(x === b)); }); });
  });
  function segValue(name) { var b = document.querySelector('[data-seg="' + name + '"] [aria-pressed="true"]'); return b ? b.dataset.v : ""; }
  function setSeg(name, v) { Array.prototype.forEach.call(document.querySelectorAll('[data-seg="' + name + '"] button'), function (x) { x.setAttribute("aria-pressed", String(v !== "" && x.dataset.v === v)); }); }
  /* ---------- ESPN (JEG-1732) ----------
     ESPN has no sign-in for other apps, so DDF never asks for the ESPN password. The flow starts from the
     league link: a public league connects at once. A private league needs ESPN's own session, which DDF
     can get three ways without seeing a password:
       - the DDF app: the app opens ESPN's sign-in in its own web view and hands this page the session;
       - the DDF helper for Chrome (staging/extension): sends the session straight to DDF's server;
       - last resort on phones: a bookmark run on espn.com.
     Or the league manager makes the league viewable to the public, and no sign-in is needed at all. */
  var EXT_ID = "hnkkhmlmjcaofnjjekgggdhchgohlkcp";
  var EXT_STORE_URL = ""; /* the helper's Chrome Web Store page, once it is listed: turns the install into one click */
  var IS_PHONE = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  var appBridge = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.ddfEspn;
  var IS_APP = !!appBridge;
  var espn = {privateId: "", busy: false};
  /* What the server says, in a fan's words. Codes come from supabase/functions/ddf-account. */
  var ESPN_SAYS = {
    espn_session_rejected: "ESPN didn't accept that sign-in. Sign in at ESPN again, then try once more.",
    espn_no_session: "Your ESPN sign-in has run out. Connect ESPN again.",
    bad_espn_s2: "ESPN's sign-in didn't come through whole. Sign in at ESPN again, then try once more.",
    bad_swid: "ESPN's sign-in didn't come through whole. Sign in at ESPN again, then try once more.",
    bad_league_id: "We couldn't find a league ID in that. Paste your league link, or just the number after leagueId=."
  };
  function espnSay(err) { return ESPN_SAYS[err && err.code] || (err && err.message) || String(err); }
  function withTeam(leagues) { return (leagues || []).map(function (l) { return Object.assign({}, l, {name: l.name + (l.team_name ? " · " + l.team_name : "")}); }); }
  function leagueUrl(id) { return "https://fantasy.espn.com/football/league?leagueId=" + encodeURIComponent(id); }

  function extCall(msg) {
    return new Promise(function (resolve) {
      try {
        if (!(window.chrome && chrome.runtime && chrome.runtime.sendMessage)) return resolve(null);
        chrome.runtime.sendMessage(EXT_ID, msg, function (r) { resolve(chrome.runtime.lastError ? null : (r || null)); });
      } catch (e) { resolve(null); }
    });
  }
  /* Lays the ESPN panel out for where the page is running: in the app or with the helper, signing in is the
     one big button and the league link folds away; otherwise the league link is the one thing on screen. */
  function layoutEspn() {
    var fast = IS_APP || !!state.ext;
    $("espn-fast").hidden = !fast;
    var block = $("espn-id-block"), home = fast ? $("espn-id-fold") : $("espn-fast").parentNode;
    if (block.parentNode !== home) { if (fast) home.appendChild(block); else home.insertBefore(block, $("espn-alt")); }
    $("espn-id-title").hidden = fast;
    $("espn-alt").hidden = fast;
    $("espn-fast-p").textContent = IS_APP ? "ESPN's own sign-in opens. Sign in there, then pick your league. DDF never sees your ESPN password."
      : "You're set up on this computer. DDF finds the leagues for the ESPN account signed in to Chrome, and never sees your ESPN password.";
    $("espn-fast").querySelector(".trail").hidden = !IS_APP;
    /* the ways in for a private league */
    $("choice-signin").hidden = !fast;
    $("choice-signin-p").textContent = IS_APP ? "ESPN's own sign-in opens. DDF never sees your ESPN password." : "DDF finds the leagues for the ESPN account signed in to Chrome. It never sees your ESPN password.";
    $("choice-helper").hidden = fast || IS_PHONE;
    $("helper-store").hidden = !EXT_STORE_URL; if (EXT_STORE_URL) $("helper-store").href = EXT_STORE_URL;
    $("ext-help").hidden = !!EXT_STORE_URL;
    $("choice-computer").hidden = fast || !IS_PHONE;
    $("espn-phone").hidden = fast || !IS_PHONE;
    $("ask-tag").textContent = fast || !IS_PHONE ? "No sign-in needed" : "Easiest on a phone";
  }
  async function detectExt() {
    var r = IS_PHONE || IS_APP ? null : await extCall({type: "ping"});
    state.ext = !!(r && r.ok);
    layoutEspn();
    return state.ext;
  }
  function showPrivate(id) {
    espn.privateId = id || "";
    $("espn-private-eyebrow").textContent = id ? "ESPN league " + id : "";
    $("espn-private-title").textContent = id ? "This league is private" : "Private league";
    $("lm-link").href = id ? leagueUrl(id) : "https://fantasy.espn.com/football/";
    $("retry-line").hidden = !id;
    $("ask-status").textContent = ""; $("self-status").textContent = "";
    $("espn-start").hidden = true; $("espn-private").hidden = false; $("picker").hidden = true;
    say("");
    $("espn-private-title").focus({preventScroll: true});
    $("connect").scrollIntoView({behavior: "smooth", block: "start"});
  }
  function showStart() { $("espn-private").hidden = true; $("espn-start").hidden = false; }
  $("espn-is-private").addEventListener("click", function () { var p = /\d{3,}/.exec($("espn-id").value); showPrivate(p ? p[0] : ""); });
  $("espn-back").addEventListener("click", function () { showStart(); $("espn-id").focus(); });

  /* The app hands back ESPN's session after the user signs in at ESPN inside it. The promise resolves
     with {espn_s2, swid}, or {cancelled: true} when the sign-in sheet is closed. */
  async function sessionFromApp() {
    var r = await appBridge.postMessage({want: "session"});
    if (!r || r.cancelled) return null;
    return {espn_s2: r.espn_s2, swid: r.swid};
  }
  async function afterEspnSession(conn, leagues) {
    showStart();
    var list = withTeam(leagues), want = espn.privateId, hit = null;
    espn.privateId = "";
    /* The league they typed first is the one they want: no second pick. */
    if (want) hit = list.filter(function (l) { return String(l.league_key).split(":")[0] === String(want) || String(l.league_key) === String(want); })[0];
    if (!hit && list.length === 1) hit = list[0];
    await loadMe();
    if (hit) return addLeague(conn, hit);
    say(list.length ? "ESPN connected. Pick your league." : "ESPN connected, but it lists no fantasy football leagues for this season.", list.length ? "ok" : "err");
    showOptions(conn, list);
  }
  async function connectEspnSignin() {
    if (espn.busy) return;
    espn.busy = true;
    try {
      if (IS_APP) {
        var keys = await sessionFromApp();
        if (!keys) { say(""); return; }
        say("Finding your ESPN leagues…");
        var j = await api("POST", "/espn/session", keys);
        keys = null;
        await afterEspnSession(j.connection, j.leagues);
      } else {
        if (!(await detectExt())) throw new Error("The DDF helper isn't in this browser yet. Add it, then try again.");
        var s = (await sb.auth.getSession()).data.session;
        if (!s) throw new Error("Sign in to DDF first.");
        say("Finding your ESPN leagues…");
        var r = await extCall({type: "connect-espn", jwt: s.access_token});
        if (!r || !r.ok) {
          if (r && r.code === "espn_signed_out") throw new Error("You're not signed in to ESPN in this browser. Sign in at espn.com in another tab, then press Connect ESPN again.");
          throw new Error((r && ESPN_SAYS[r.code]) || "The DDF helper didn't answer. Reload this page and try again.");
        }
        await afterEspnSession(r.connection, r.leagues);
      }
    } catch (err) { say(espnSay(err), "err"); } finally { espn.busy = false; }
  }
  ["espn-go", "espn-go2"].forEach(function (id) { $(id).addEventListener("click", busy($(id), connectEspnSignin)); });
  $("helper-check").addEventListener("click", busy($("helper-check"), async function () {
    if (await detectExt()) { say("The DDF helper is ready.", "ok"); return; }
    throw new Error("We can't see the DDF helper yet. Finish the steps, reload this page, and try again.");
  }));

  /* From the league link: public leagues connect at once; a private one opens the ways in. */
  async function connectEspnLeague(text) {
    var id = (/\d{3,}/.exec(text) || [""])[0];
    say("Looking up your league…");
    var j;
    try { j = await api("POST", "/espn/connect", {league_id: text}); }
    catch (err) {
      if (err.code === "espn_private") { showPrivate(id); return false; }
      throw new Error(espnSay(err));
    }
    showStart();
    await loadMe();
    var list = j.leagues.map(function (l) { return Object.assign({}, l, {season: j.season}); });
    if (list.length === 1) await addLeague(j.connection, list[0]);
    else { say("Connected " + j.connection.display_name + ".", "ok"); showOptions(j.connection, list); }
    return true;
  }
  $("espn-form").addEventListener("submit", busy(null, async function () { await connectEspnLeague($("espn-id").value.trim()); }));
  $("espn-retry").addEventListener("click", busy($("espn-retry"), async function () {
    var ok = await connectEspnLeague(espn.privateId);
    if (!ok) say("ESPN still shows this league as private. Once your league manager flips the switch, try again.", "err");
  }));

  /* One tap: a ready-to-send note for the league manager, with the exact steps. */
  function managerNote() {
    var id = espn.privateId;
    return "Could you make our ESPN league viewable to the public? I want to use Data Driven Football for trade values and lineup help, and it can only read leagues with that switched on. It only lets people look; nobody can change anything.\n\n" +
      "It takes about 30 seconds:\n1. Open the league at " + (id ? leagueUrl(id) : "fantasy.espn.com") + "\n2. LM Tools > Basic Settings > Edit\n3. Set \"Make League Viewable to Public\" to Yes and save\n\nThanks!";
  }
  async function shareOrCopy(payload, statusEl, copiedText) {
    if (navigator.share) {
      try { await navigator.share(payload); statusEl.textContent = ""; return; }
      catch (e) { if (e && e.name === "AbortError") return; }
    }
    var text = payload.text || payload.url;
    try { await navigator.clipboard.writeText(text); statusEl.textContent = copiedText; }
    catch (e) { window.prompt("Copy this:", text); }
  }
  $("ask-share").addEventListener("click", function () { shareOrCopy({text: managerNote()}, $("ask-status"), "Copied. Paste it in your league chat or a text."); });
  $("send-self").addEventListener("click", function () { shareOrCopy({title: "Add your league to DDF", url: HERE}, $("self-status"), "Link copied."); });

  /* Last resort on phones: a bookmark run on espn.com reads ESPN's own sign-in and comes back to this
     page in the same tab with it in the URL fragment, which never reaches a server. A head script takes
     it out of the address bar at once; this page sends it to DDF's server and forgets it. */
  var BOOKMARKLET = "javascript:(function(){" +
    "if(!/(^|[.])espn[.]com$/.test(location.hostname)){alert('Open espn.com first, signed in, then tap DDF ESPN.');return}" +
    "var g=function(n){var m=document.cookie.match(new RegExp('(?:^|; )'+n+'=([^;]*)'));return m?m[1]:''};" +
    "var s2=g('espn_s2'),sw=decodeURIComponent(g('SWID'));" +
    "var inEspn=!!(window.espn&&espn.core&&espn.core.loggedIn);" +
    "if(!s2&&inEspn){alert('ESPN shows you signed in, but did not let DDF read your sign-in. Tell DDF (code s2-hidden).');return}" +
    "if(!s2||!sw){alert('Sign in to ESPN first, then tap DDF ESPN again.');return}" +
    "location.href='" + HERE + "#espn='+encodeURIComponent(btoa(JSON.stringify({espn_s2:s2,swid:sw})))})()";
  $("bm-code").value = BOOKMARKLET;
  $("bm-copy").addEventListener("click", function () {
    var done = function () { $("bm-copied").textContent = "Copied"; };
    try { navigator.clipboard.writeText(BOOKMARKLET).then(done, function () { $("bm-code").select(); }); } catch (e) { $("bm-code").select(); }
  });
  $("espn-open").addEventListener("click", function () { location.href = "https://www.espn.com/fantasy/football/"; });
  async function finishEspnHandoff() {
    var raw = window.__ddfEspnHandoff;
    try { if (!raw) raw = sessionStorage.getItem("ddf_espn_pending"); } catch (e) { /* none */ }
    if (!raw) return;
    var keys;
    try { keys = JSON.parse(atob(decodeURIComponent(raw))); } catch (e) { window.__ddfEspnHandoff = null; say("That ESPN sign-in didn't come through. Tap the DDF ESPN bookmark again on espn.com.", "err"); return; }
    var s = (await sb.auth.getSession()).data.session;
    if (!s) { try { sessionStorage.setItem("ddf_espn_pending", raw); } catch (e) { /* ignore */ } say("Sign in to DDF in this tab to finish connecting ESPN.", "ok"); return; }
    window.__ddfEspnHandoff = null;
    try { sessionStorage.removeItem("ddf_espn_pending"); } catch (e) { /* ignore */ }
    say("Finding your ESPN leagues…");
    try { var j = await api("POST", "/espn/session", {espn_s2: keys.espn_s2, swid: keys.swid}); await afterEspnSession(j.connection, j.leagues); }
    catch (err) { throw new Error(espnSay(err)); }
  }
  var DEV = false;
  try { DEV = localStorage.getItem("ddf_dev") === "1"; } catch (e) { /* dev paths stay hidden */ }
  $("espn-dev").hidden = !DEV; $("dev-views").hidden = !DEV;
  $("espn-private-form").addEventListener("submit", busy(null, async function () {
    var j = await api("POST", "/espn/connect", {league_id: $("espn-pid").value.trim(), espn_s2: $("espn-s2").value.trim(), swid: $("espn-swid").value.trim()});
    $("espn-s2").value = ""; $("espn-swid").value = "";
    say("Connected ESPN league " + j.connection.display_name + ".", "ok");
    showOptions(j.connection, j.leagues);
    await loadMe();
  }));
  $("yahoo").addEventListener("click", busy($("yahoo"), async function () {
    var j = await api("POST", "/yahoo/start", {return_to: HERE});
    location.href = j.url;
  }));

  async function addLeague(conn, l) {
    say("Reading " + l.name + " from " + (NAMES[conn.platform] || conn.platform) + "…");
    var j = await api("POST", "/leagues", {connection_id: conn.id, league_key: l.league_key, season: l.season});
    say("Added " + j.league.name + ". Now pick your team.", "ok");
    $("picker").hidden = true;
    await loadMe();
    openLeague(j.league);
  }
  function showOptions(conn, leagues) {
    var ul = $("league-options");
    ul.textContent = "";
    if (!leagues || !leagues.length) ul.appendChild(el("li", {text: "No leagues found for this season."}));
    (leagues || []).forEach(function (l) {
      ul.appendChild(el("li", {},
        el("span", {}, el("strong", {text: l.name}), el("small", {class: "muted", text: "  " + [l.season, l.teams ? l.teams + " teams" : null].filter(Boolean).join(" · ")})),
        el("button", {class: "primary big", type: "button", text: "Add this league", onclick: busy(null, async function (e) {
          e.target.disabled = true;
          try { await addLeague(conn, l); } catch (err) { throw new Error(conn.platform === "espn" ? espnSay(err) : err.message); }
        })})));
    });
    $("picker").hidden = false;
    step("connect");
    $("picker").scrollIntoView({behavior: "smooth", block: "start"});
  }

  /* ---------- account state ---------- */
  async function loadMe() {
    state.me = await api("GET", "/me");
    $("who").textContent = state.me.user.email || "";
    $("yahoo-note").textContent = state.me.yahoo_configured
      ? "Official Yahoo sign-in. Until Yahoo approves DDF's app for its Fantasy API, Yahoo connects but leagues can't be read yet."
      : "Not ready yet: DDF's Yahoo app keys aren't in place. That's a one-time setup step on our side.";
    $("yahoo").disabled = !state.me.yahoo_configured;
    var cl = $("conn-list");
    cl.textContent = "";
    $("mine").hidden = !state.me.connections.length && !state.me.leagues.length;
    state.me.connections.forEach(function (c) {
      cl.appendChild(el("li", {},
        el("span", {}, el("strong", {text: NAMES[c.platform] || c.platform}), " " + (c.display_name || ""), el("small", {class: "muted", text: "  since " + when(c.created_at)})),
        el("span", {class: "cluster"},
          el("button", {type: "button", text: "Leagues", onclick: busy(null, async function () { var j = await api("GET", "/connections/" + c.id + "/leagues"); showOptions(c, j.leagues.map(function (l) { return Object.assign({season: j.season}, l); })); })}),
          el("button", {type: "button", class: "danger", text: "Disconnect", onclick: busy(null, async function () {
            if (!confirm("Disconnect " + (NAMES[c.platform] || c.platform) + "? This deletes its stored sign-in and its leagues.")) return;
            await api("DELETE", "/connections/" + c.id);
            if (IS_APP && c.platform === "espn") { try { await appBridge.postMessage({want: "forget"}); } catch (e) { /* the app's ESPN sign-in stays until it expires */ } }
            say("Disconnected " + (NAMES[c.platform] || c.platform) + ".", "ok"); $("league").hidden = true; await loadMe();
          })}))));
    });
    var ll = $("league-list");
    ll.textContent = "";
    if (!state.me.leagues.length && state.me.connections.length) ll.appendChild(el("li", {class: "muted", text: "No leagues added yet. Press Leagues above to pick one."}));
    state.me.leagues.forEach(function (l) {
      ll.appendChild(el("li", {},
        el("span", {}, el("strong", {text: l.name || l.league_key}), el("small", {class: "muted", text: "  " + (l.source === "flaim" ? (NAMES[l.platform] || l.platform) + " via Flaim (stand-in until Yahoo is approved) · pulled " : (NAMES[l.platform] || l.platform) + " · updated ") + when(l.pulled_at) + (l.confirmed_at ? " · settings confirmed" : "")})),
        el("span", {class: "cluster"},
          l.my_team_key ? el("a", {class: "button", href: "plan.html?league=" + encodeURIComponent(l.id), text: "Season Plan"}) : null, /* same tab: the session is in this tab's sessionStorage */
          el("button", {type: "button", text: "Open", onclick: busy(null, async function () { var j = await api("GET", "/leagues/" + l.id); openLeague(j.league); })}))));
    });
    if (!state.league) step("connect");
  }

  /* ---------- one league ---------- */
  var ROSTER_KEYS = ["QB", "RB", "WR", "TE", "FLEX", "BENCH", "K", "DST"];
  function openLeague(lg) {
    state.league = lg;
    var s = lg.summary;
    $("league").hidden = false;
    $("lg-title").textContent = s.name;
    /* Say honestly where the data came from (JEG-1732: Flaim stands in until Yahoo approves DDF's app). */
    var viaFlaim = lg.source === "flaim" || (s.source && s.source.kind === "flaim");
    $("lg-meta").textContent = (viaFlaim ? "League data via Flaim (stand-in until Yahoo is approved) · pulled " + when(lg.pulled_at)
      : (NAMES[s.platform] || s.platform) + " · " + s.season + " · updated " + when(lg.pulled_at)) + (s.current_week ? " · week " + s.current_week : "");
    $("refresh").hidden = viaFlaim;
    var list = $("team-pick-list");
    list.textContent = "";
    s.teams.forEach(function (t) {
      var input = el("input", {type: "radio", name: "my-team", value: t.team_key});
      if (t.team_key === lg.my_team_key) input.checked = true;
      input.addEventListener("change", busy(null, async function () {
        var j = await api("POST", "/leagues/" + state.league.id + "/team", {team_key: t.team_key});
        say("Saved: " + t.name + " is your team.", "ok"); openLeague(j.league);
      }));
      var mgr = t.managers.length && t.managers[0].name ? t.managers[0].name : "";
      list.appendChild(el("label", {class: "team-pick-option" + (input.checked ? " selected" : "")}, input,
        el("span", {class: "team-pick-text"}, el("strong", {text: t.name}), mgr ? el("small", {text: mgr}) : null)));
    });
    /* Only what the platform gave (or the user confirmed) is filled in; anything else is blank and must be chosen. */
    var conf = lg.confirmed_settings || s.settings.ddf || {};
    var unread = [];
    setSeg("scoring", conf.scoring || ""); if (!conf.scoring) unread.push("scoring");
    setSeg("teams", conf.teams ? String(conf.teams) : ""); if (!conf.teams) unread.push("team count");
    setSeg("superflex", typeof conf.superflex === "boolean" ? (conf.superflex ? "yes" : "no") : ""); if (typeof conf.superflex !== "boolean") unread.push("superflex");
    var grid = $("s-roster");
    grid.textContent = "";
    ROSTER_KEYS.forEach(function (k) {
      var v = conf.roster ? conf.roster[k] : null;
      grid.appendChild(el("label", {}, k === "DST" ? "DEF" : k === "BENCH" ? "Bench" : k, el("input", {type: "number", min: "0", max: k === "K" || k === "DST" ? "3" : "20", id: "r-" + k, value: v == null ? "" : String(v)})));
    });
    if (!conf.roster) unread.push("roster slots");
    $("unread-note").textContent = unread.length ? "Not read from " + (NAMES[s.platform] || s.platform) + ": " + unread.join(", ") + ". Choose these before confirming." : "";
    var fit = s.settings.fit;
    $("settings-help").textContent = "Read from the league. Once you confirm, these drive DDF for this league." + (fit ? " DDF can't reflect everything here: " + Object.keys(fit).map(function (k) { return k + " " + JSON.stringify(fit[k]); }).join(", ") + "." : "");
    $("confirmed-at").textContent = lg.confirmed_at ? "Confirmed " + when(lg.confirmed_at) : "Not confirmed yet";
    renderView();
    step(!lg.my_team_key ? "team" : !lg.confirmed_at ? "settings" : "done");
    $("league").scrollIntoView({behavior: "smooth", block: "start"});
  }

  $("settings-form").addEventListener("submit", busy(null, async function () {
    var missing = [], roster = {};
    if (!segValue("scoring")) missing.push("scoring");
    if (!segValue("teams")) missing.push("team count");
    if (!segValue("superflex")) missing.push("superflex");
    ROSTER_KEYS.forEach(function (k) { var v = $("r-" + k).value.trim(); if (v === "") missing.push(k === "DST" ? "DEF" : k); else roster[k] = Number(v); });
    if (missing.length) throw new Error("Choose " + missing.join(", ") + " before confirming.");
    var settings = {scoring: segValue("scoring"), superflex: segValue("superflex") === "yes", teams: Number(segValue("teams")), roster: roster};
    if (settings.superflex && state.league.summary.settings.ddf && state.league.summary.settings.ddf.superflexSlots) settings.superflexSlots = state.league.summary.settings.ddf.superflexSlots;
    var j = await api("POST", "/leagues/" + state.league.id + "/confirm", {settings: settings});
    say("Settings confirmed.", "ok"); openLeague(j.league); await loadMe();
  }));
  $("refresh").addEventListener("click", busy($("refresh"), async function () {
    say("Refreshing from " + (NAMES[state.league.platform] || state.league.platform) + "…");
    var j = await api("POST", "/leagues/" + state.league.id + "/refresh");
    say("Refreshed.", "ok"); openLeague(j.league); await loadMe();
  }));
  $("close-league").addEventListener("click", function () { $("league").hidden = true; state.league = null; });
  $("delete-league").addEventListener("click", busy($("delete-league"), async function () {
    if (!confirm("Remove " + state.league.name + " from your DDF account?")) return;
    await api("DELETE", "/leagues/" + state.league.id); $("league").hidden = true; state.league = null; say("Removed.", "ok"); await loadMe();
  }));
  $("delete-account").addEventListener("click", busy($("delete-account"), async function () {
    if (!confirm("Delete your DDF account, every connection and every pulled league? This cannot be undone.")) return;
    await api("DELETE", "/account"); await sb.auth.signOut(); say("Your DDF account is deleted.", "ok"); render();
  }));
  $("raw").addEventListener("click", busy($("raw"), async function () {
    var j = await api("GET", "/leagues/" + state.league.id + "?raw=1");
    state.view = "json"; renderView(j.league.raw);
  }));
  Array.prototype.forEach.call(document.querySelectorAll("button[data-view]"), function (b) {
    b.addEventListener("click", function () { state.view = b.dataset.view; renderView(); });
  });

  function renderView(raw) {
    Array.prototype.forEach.call(document.querySelectorAll("[data-view]"), function (b) { b.setAttribute("aria-pressed", String(b.dataset.view === state.view)); });
    $("plain").hidden = state.view !== "plain";
    $("json").hidden = state.view !== "json";
    if (state.view === "json") { $("json").textContent = JSON.stringify(raw || state.league.summary, null, 2); return; }
    var s = state.league.summary, mine = state.league.my_team_key, box = $("plain");
    box.textContent = "";
    var set = s.settings, td = set.trade_deadline;
    var dl = el("dl", {class: "kv"});
    [["Teams", set.num_teams], ["Scoring DDF reads", set.ddf ? set.ddf.scoring + (set.ddf.superflex ? ", superflex" : "") : null],
      ["Starting lineup", set.roster_positions.filter(function (p) { return p !== "BN" && p !== "IR"; }).join(" ")],
      ["Trade deadline", td.none ? "none" : td.week ? "week " + td.week : td.date],
      ["Waivers", set.waiver_type], ["FAAB budget", set.faab_budget], ["Regular season ends", set.last_regular_week ? "week " + set.last_regular_week : null],
      ["Playoffs", set.playoff_start_week ? set.playoff_teams + " teams from week " + set.playoff_start_week : null]
    ].forEach(function (r) { dl.appendChild(el("dt", {text: r[0]})); dl.appendChild(el("dd", {text: r[1] == null || r[1] === "" ? "—" : String(r[1])})); });
    box.appendChild(el("h3", {text: "Settings", style: "margin-top:18px"}));
    box.appendChild(dl);

    var head = el("tr", {}, el("th", {text: "#"}), el("th", {text: "Team"}), el("th", {text: "W-L-T"}), el("th", {class: "number", text: "PF"}), el("th", {class: "number", text: "PA"}), el("th", {class: "number", text: "FAAB"}), el("th", {class: "number", text: "Waiver"}));
    var body = el("tbody");
    s.teams.slice().sort(function (a, b) { return (a.standings.rank || 99) - (b.standings.rank || 99); }).forEach(function (t) {
      var st = t.standings;
      body.appendChild(el("tr", {class: t.team_key === mine ? "mine" : ""}, el("td", {text: st.rank == null ? "—" : String(st.rank)}), el("td", {text: t.name}),
        el("td", {text: st.wins == null ? "—" : st.wins + "-" + st.losses + "-" + (st.ties == null ? "—" : st.ties)}), el("td", {class: "number", text: st.points_for == null ? "—" : String(st.points_for)}),
        el("td", {class: "number", text: st.points_against == null ? "—" : String(st.points_against)}), el("td", {class: "number", text: t.faab_remaining == null ? "—" : String(t.faab_remaining)}),
        el("td", {class: "number", text: t.waiver_priority == null ? "—" : String(t.waiver_priority)})));
    });
    box.appendChild(el("h3", {text: "Standings", style: "margin-top:22px"}));
    box.appendChild(el("div", {class: "table-wrap"}, el("table", {}, el("thead", {}, head), body)));

    var me = s.teams.filter(function (t) { return t.team_key === mine; })[0];
    if (me) {
      var rb = el("tbody");
      me.roster.forEach(function (p) {
        rb.appendChild(el("tr", {}, el("td", {text: p.slot || "—"}), el("td", {text: p.name || ("id " + p.player_id)}), el("td", {text: [p.position, p.nfl_team].filter(Boolean).join(" · ") || "—"}), el("td", {text: p.status || ""})));
      });
      box.appendChild(el("h3", {text: "Your roster: " + me.name, style: "margin-top:22px"}));
      box.appendChild(el("div", {class: "table-wrap"}, el("table", {}, el("thead", {}, el("tr", {}, el("th", {text: "Slot"}), el("th", {text: "Player"}), el("th", {text: "Pos · NFL"}), el("th", {text: "Status"}))), rb)));

      var names = {};
      s.teams.forEach(function (t) { names[t.team_key] = t.name; });
      var sb2 = el("tbody");
      s.schedule.forEach(function (w) {
        w.matchups.forEach(function (m) {
          var i = m.team_keys.indexOf(mine);
          if (i < 0) return;
          var o = 1 - i;
          var fmt = function (x) { return x == null ? "—" : String(x); };
          sb2.appendChild(el("tr", {}, el("td", {text: String(w.week)}), el("td", {text: names[m.team_keys[o]] || "—"}),
            el("td", {class: "number", text: fmt(m.points[i]) + " – " + fmt(m.points[o])}),
            el("td", {class: "number", text: m.projected_points[i] == null ? "—" : fmt(m.projected_points[i]) + " – " + fmt(m.projected_points[o])})));
        });
      });
      box.appendChild(el("h3", {text: "Your schedule", style: "margin-top:22px"}));
      box.appendChild(el("div", {class: "table-wrap"}, el("table", {}, el("thead", {}, el("tr", {}, el("th", {text: "Wk"}), el("th", {text: "Opponent"}), el("th", {class: "number", text: "Score"}), el("th", {class: "number", text: "Platform projection"}))), sb2)));
    } else {
      box.appendChild(el("p", {class: "muted", text: "Pick your team above to see your roster and schedule."}));
    }
    if (s.missing.length) {
      var ul = el("ul");
      s.missing.forEach(function (m) { ul.appendChild(el("li", {}, el("span", {class: "mono", text: m.path}), " — " + m.reason)); });
      box.appendChild(el("h3", {text: "Not available from " + (NAMES[s.platform] || s.platform), style: "margin-top:22px"}));
      box.appendChild(ul);
    }
    if (s.probes && DEV) {
      box.appendChild(el("h3", {text: "Yahoo projection probe", style: "margin-top:22px"}));
      box.appendChild(el("pre", {text: JSON.stringify(s.probes, null, 2)}));
    }
    if (DEV) box.appendChild(el("p", {class: "muted"}, el("small", {text: "Sources: " + s.sources.join(", ")})));
  }

  /* ---------- boot ---------- */
  async function render() {
    var session = (await sb.auth.getSession()).data.session;
    $("signin").hidden = !!session;
    $("app").hidden = !session;
    if (!session) { step("signin"); return; }
    try { await loadMe(); } catch (err) { say(err.message, "err"); }
    placePill();
    detectExt();
    finishEspnHandoff().catch(function (err) { say(err.message, "err"); });
  }
  var h = new URLSearchParams(location.hash.slice(1));
  var handoff = h.get("yahoo") === "finish" ? h.get("h") : null;
  if (handoff) {
    /* The callback parked the Yahoo tokens; they attach only to the DDF account signed in here. */
    history.replaceState(null, "", HERE);
    (async function () {
      try { await api("POST", "/yahoo/finish", {handoff: handoff}); say("Yahoo connected. Press Leagues next to Yahoo to pick a league.", "ok"); await loadMe(); }
      catch (err) { say(err.message, "err"); }
    })();
  }
  else if (h.get("yahoo") === "error") say("Yahoo did not connect (" + (h.get("code") || "error") + "). Try again.", "err");
  else if (h.get("error_description")) say(h.get("error_description"), "err");
  if (h.get("yahoo")) history.replaceState(null, "", HERE);
  sb.auth.onAuthStateChange(function (evt) { if (evt === "SIGNED_IN" || evt === "SIGNED_OUT") render(); });
  render();
})();
