/* DDF staging: sign in › connect › pick league and team › confirm settings › view (JEG-1732).
 * Every platform string is written with textContent, never as HTML. */
(function () {
  "use strict";
  var SUPABASE_URL = "https://iskiybsimubiujwuchsl.supabase.co";
  var PUBLISHABLE_KEY = "sb_publishable_pzHxlyPf-jZFpStnejUUsQ_OaYuj4j7"; /* public by design */
  var FN = window.DDF_STAGING_FN || SUPABASE_URL + "/functions/v1/ddf-account"; /* override only in the local test harness */
  var HERE = location.origin + location.pathname;
  var sb = window.supabase.createClient(SUPABASE_URL, PUBLISHABLE_KEY, {auth: {flowType: "implicit", detectSessionInUrl: true, persistSession: true}});
  var $ = function (id) { return document.getElementById(id); };
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
    var order = ["signin", "connect", "league", "team", "settings", "view"], at = order.indexOf(name);
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
    if (!r.ok) throw new Error((j.error && j.error.message) || ("DDF answered " + r.status));
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
    var res = await sb.auth.signInWithOtp({email: email, options: {emailRedirectTo: HERE}});
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
  $("espn-form").addEventListener("submit", busy(null, async function () {
    var season = Number($("espn-season").value) || undefined;
    var j = await api("POST", "/espn/connect", {league_id: $("espn-id").value.trim(), season: season});
    say("Connected ESPN league " + j.connection.display_name + ".", "ok");
    showOptions(j.connection, j.leagues.map(function (l) { return Object.assign({}, l, {season: j.season}); }));
    await loadMe();
  }));
  $("yahoo").addEventListener("click", busy($("yahoo"), async function () {
    var j = await api("POST", "/yahoo/start", {return_to: HERE});
    location.href = j.url;
  }));

  function showOptions(conn, leagues) {
    var ul = $("league-options");
    ul.textContent = "";
    if (!leagues || !leagues.length) ul.appendChild(el("li", {text: "No leagues found for this season."}));
    (leagues || []).forEach(function (l) {
      ul.appendChild(el("li", {},
        el("span", {}, el("strong", {text: l.name}), el("small", {class: "muted", text: "  " + [l.season, l.teams ? l.teams + " teams" : null].filter(Boolean).join(" · ")})),
        el("button", {class: "primary", type: "button", text: "Pull this league", onclick: busy(null, async function (e) {
          e.target.disabled = true;
          say("Pulling " + l.name + " from " + conn.platform + "…");
          var j = await api("POST", "/leagues", {connection_id: conn.id, league_key: l.league_key, season: l.season});
          say("Pulled " + j.league.name + ".", "ok");
          $("picker").hidden = true;
          await loadMe();
          openLeague(j.league);
        })})));
    });
    $("picker").hidden = false;
    step("league");
    $("picker").scrollIntoView({behavior: "smooth", block: "start"});
  }

  /* ---------- account state ---------- */
  async function loadMe() {
    state.me = await api("GET", "/me");
    $("who").textContent = state.me.user.email || "";
    $("yahoo-note").firstChild.textContent = state.me.yahoo_configured
      ? "Official Yahoo sign-in. Yahoo must approve DDF's app before leagues can be read."
      : "Not set up yet: DDF's Yahoo app keys are not in place.";
    $("yahoo").disabled = !state.me.yahoo_configured;
    var cl = $("conn-list");
    cl.textContent = "";
    if (!state.me.connections.length) cl.appendChild(el("li", {class: "muted", text: "Nothing connected yet."}));
    state.me.connections.forEach(function (c) {
      cl.appendChild(el("li", {},
        el("span", {}, el("strong", {text: c.platform[0].toUpperCase() + c.platform.slice(1)}), " " + (c.display_name || ""), el("small", {class: "muted", text: "  since " + when(c.created_at)})),
        el("span", {class: "cluster"},
          el("button", {type: "button", text: "Leagues", onclick: busy(null, async function () { var j = await api("GET", "/connections/" + c.id + "/leagues"); showOptions(c, j.leagues.map(function (l) { return Object.assign({season: j.season}, l); })); })}),
          el("button", {type: "button", class: "danger", text: "Disconnect", onclick: busy(null, async function () {
            if (!confirm("Disconnect " + c.platform + "? This deletes its stored sign-in and its pulled leagues.")) return;
            await api("DELETE", "/connections/" + c.id); say("Disconnected " + c.platform + ".", "ok"); $("league").hidden = true; await loadMe();
          })}))));
    });
    var ll = $("league-list");
    ll.textContent = "";
    if (!state.me.leagues.length) ll.appendChild(el("li", {class: "muted", text: "No leagues pulled yet."}));
    state.me.leagues.forEach(function (l) {
      ll.appendChild(el("li", {},
        el("span", {}, el("strong", {text: l.name || l.league_key}), el("small", {class: "muted", text: "  " + l.platform + " · pulled " + when(l.pulled_at) + (l.confirmed_at ? " · settings confirmed" : "")})),
        el("button", {type: "button", text: "Open", onclick: busy(null, async function () { var j = await api("GET", "/leagues/" + l.id); openLeague(j.league); })})));
    });
    if (!state.league) step(state.me.connections.length ? (state.me.leagues.length ? "league" : "connect") : "connect");
  }

  /* ---------- one league ---------- */
  var ROSTER_KEYS = ["QB", "RB", "WR", "TE", "FLEX", "BENCH", "K", "DST"];
  function openLeague(lg) {
    state.league = lg;
    var s = lg.summary;
    $("league").hidden = false;
    $("lg-platform").textContent = s.platform + " · " + s.season + " · " + s.league_key;
    $("lg-name").textContent = s.name;
    $("lg-pulled").textContent = "Pulled " + when(lg.pulled_at) + (s.current_week ? " · week " + s.current_week : "");
    var sel = $("team-select");
    sel.textContent = "";
    sel.appendChild(el("option", {value: "", text: "Choose your team"}));
    s.teams.forEach(function (t) {
      var o = el("option", {value: t.team_key, text: t.name + (t.managers.length && t.managers[0].name ? " (" + t.managers[0].name + ")" : "")});
      if (t.team_key === lg.my_team_key) o.selected = true;
      sel.appendChild(o);
    });
    var conf = lg.confirmed_settings || s.settings.ddf || {scoring: "ppr", superflex: false};
    $("s-scoring").value = conf.scoring;
    $("s-teams").value = String(conf.teams || 12);
    $("s-sf").checked = !!conf.superflex;
    var grid = $("s-roster");
    grid.textContent = "";
    ROSTER_KEYS.forEach(function (k) {
      var v = conf.roster ? conf.roster[k] : "";
      grid.appendChild(el("label", {}, k === "DST" ? "DEF" : k === "BENCH" ? "Bench" : k, el("input", {type: "number", min: "0", max: k === "K" || k === "DST" ? "3" : "20", id: "r-" + k, value: v == null ? "" : String(v)})));
    });
    var fit = s.settings.fit;
    $("fit-note").textContent = fit ? ("DDF can't reflect everything here: " + Object.keys(fit).map(function (k) { return k + " " + JSON.stringify(fit[k]); }).join(", ") + ".") : "";
    $("confirmed-at").textContent = lg.confirmed_at ? "Confirmed " + when(lg.confirmed_at) : "Not confirmed yet";
    renderView();
    step(!lg.my_team_key ? "team" : !lg.confirmed_at ? "settings" : "view");
    $("league").scrollIntoView({behavior: "smooth", block: "start"});
  }

  $("team-form").addEventListener("submit", busy(null, async function () {
    var key = $("team-select").value;
    if (!key) throw new Error("Choose your team first.");
    var j = await api("POST", "/leagues/" + state.league.id + "/team", {team_key: key});
    say("Saved your team.", "ok"); openLeague(j.league);
  }));
  $("settings-form").addEventListener("submit", busy(null, async function () {
    var roster = {}, any = false;
    ROSTER_KEYS.forEach(function (k) { var v = $("r-" + k).value; if (v !== "") any = true; roster[k] = Number(v || 0); });
    var settings = {scoring: $("s-scoring").value, superflex: $("s-sf").checked, teams: Number($("s-teams").value)};
    if (settings.superflex && state.league.summary.settings.ddf && state.league.summary.settings.ddf.superflexSlots) settings.superflexSlots = state.league.summary.settings.ddf.superflexSlots;
    if (any) settings.roster = roster;
    var j = await api("POST", "/leagues/" + state.league.id + "/confirm", {settings: settings});
    say("Settings confirmed.", "ok"); openLeague(j.league); await loadMe();
  }));
  $("refresh").addEventListener("click", busy($("refresh"), async function () {
    say("Refreshing from " + state.league.platform + "…");
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
  Array.prototype.forEach.call(document.querySelectorAll("[data-view]"), function (b) {
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
        el("td", {text: st.wins == null ? "—" : st.wins + "-" + st.losses + "-" + (st.ties || 0)}), el("td", {class: "number", text: st.points_for == null ? "—" : String(st.points_for)}),
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
      box.appendChild(el("h3", {text: "Not available from " + s.platform, style: "margin-top:22px"}));
      box.appendChild(ul);
    }
    if (s.probes) {
      box.appendChild(el("h3", {text: "Yahoo projection probe", style: "margin-top:22px"}));
      box.appendChild(el("pre", {text: JSON.stringify(s.probes, null, 2)}));
    }
    box.appendChild(el("p", {class: "muted"}, el("small", {text: "Sources: " + s.sources.join(", ")})));
  }

  /* ---------- boot ---------- */
  async function render() {
    var session = (await sb.auth.getSession()).data.session;
    $("signin").hidden = !!session;
    $("app").hidden = !session;
    if (!session) { step("signin"); return; }
    try { await loadMe(); } catch (err) { say(err.message, "err"); }
  }
  var h = new URLSearchParams(location.hash.slice(1));
  if (h.get("yahoo") === "connected") say("Yahoo connected. Press Leagues next to Yahoo to pick a league.", "ok");
  else if (h.get("yahoo") === "error") say("Yahoo did not connect (" + (h.get("code") || "error") + "). Try again.", "err");
  else if (h.get("error_description")) say(h.get("error_description"), "err");
  if (h.get("yahoo")) history.replaceState(null, "", HERE);
  sb.auth.onAuthStateChange(function (evt) { if (evt === "SIGNED_IN" || evt === "SIGNED_OUT") render(); });
  render();
})();
