/* DDF staging: Games left (JEG-1736). Renders DDFWeekly.plan(summary, weekly, {}) as documented in
 * docs/signed-in-features.md. Every league string is written with textContent, never as HTML.
 * A missing value is never 0: null renders as "—" with its reason. */
(function () {
  "use strict";
  var SUPABASE_URL = "https://iskiybsimubiujwuchsl.supabase.co";
  var PUBLISHABLE_KEY = "sb_publishable_pzHxlyPf-jZFpStnejUUsQ_OaYuj4j7"; /* public by design */
  var FN = window.DDF_STAGING_FN || SUPABASE_URL + "/functions/v1/ddf-account"; /* override only in the local test harness */
  var QS = new URLSearchParams(location.search);
  var IS_LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  var MOCK = IS_LOCAL && QS.get("mock") === "1"; /* sample plan, local preview only */
  var MOCK_URL = "../harness/fixtures/plan-sample.json";
  var sb = null;
  var $ = function (id) { return document.getElementById(id); };

  function el(tag, attrs) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] == null) return;
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) { var c = arguments[i]; if (c != null && c !== false) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    return n;
  }
  async function api(method, path) {
    var s = (await sb.auth.getSession()).data.session;
    if (!s) throw new Error("Sign in first.");
    var r = await fetch(FN + path, {method: method, headers: {authorization: "Bearer " + s.access_token, apikey: PUBLISHABLE_KEY, "content-type": "application/json"}});
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok) { var err = new Error((j.error && j.error.message) || "Something went wrong on our side. Try again in a minute."); err.code = (j.error && j.error.code) || ""; throw err; }
    return j;
  }

  /* ---------- formatting ---------- */
  var isNum = function (x) { return typeof x === "number" && isFinite(x); };
  function na(reason) { var r = reason || "Not available"; return el("span", {class: "na", title: r, "aria-label": "Not available. " + r, text: "—"}); }
  function one(x, reason) { return isNum(x) ? x.toFixed(1) : na(reason); }
  function pctText(p) {
    if (!isNum(p)) return null;
    var v = Math.round(p * 100);
    if (v === 0 && p > 0) return "<1%";
    if (v === 100 && p < 1) return ">99%";
    return v + "%";
  }
  function pct(p, reason) { var t = pctText(p); return t == null ? na(reason) : t; }
  function signed(x) { return (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(1); }
  function ordinal(n) { if (!isNum(n)) return null; var s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function record(t) { return !t || !isNum(t.wins) || !isNum(t.losses) ? null : t.wins + "-" + t.losses + (t.ties ? "-" + t.ties : ""); }
  function when(iso) {
    if (!iso) return null;
    if (!/^\d{4}-\d\d-\d\d/.test(iso)) return String(iso); /* already words */
    var d = new Date(iso);
    if (isNaN(d)) return String(iso);
    return /T/.test(iso) ? d.toLocaleString(undefined, {weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit"})
      : d.toLocaleDateString(undefined, {month: "short", day: "numeric", timeZone: "UTC"});
  }
  function whenFull(iso) { var d = new Date(iso); return isNaN(d) ? String(iso) : d.toLocaleString(undefined, {month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"}); }
  var TYPES = {must_win: "Must-win", bankable: "Bankable", favored: "Favored", uphill: "Uphill", seed_game: "Seed game", free: "Free", playoff: "Playoff"};
  var GOAL_SHORT = {high_score: "High score", record: "Record", seed: "Seed", playoffs: "Playoffs"};
  var KINDS = {start: "Start", add: "Add", watch: "Watch", bye: "Bye"};
  var STATUS = {midevent: "In progress", live: "In progress", postevent: "Final", final: "Final"};
  var SOURCES = {espn: "ESPN", sleeper: "Sleeper", espn_live: "ESPN live"};
  /* Why a figure is missing, from plan.missing, when one entry names this week. */
  function missingFor(plan, week) {
    var hit = (plan.missing || []).filter(function (m) { return new RegExp("\\bweeks? [^.]*\\b" + week + "\\b").test(m.what || ""); })[0];
    return hit ? hit.reason : null;
  }

  /* Data age (JEG-1736): the league data is a snapshot that does not refresh by itself, so every page says how old it
   * is. Attention when it is over 6 hours old, or when a game of the current week has kicked off since the pull.
   * league-bridge.js carries the same function for Team, Find and Build (this page does not load the bridge). */
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
  var AGE_STYLE = "margin:0 0 16px;font-size:13px;line-height:1.45;color:var(--muted)";
  var AGE_STALE = "margin:0 0 16px;font-size:13px;line-height:1.45;padding:8px 12px;border-left:3px solid var(--attention-text);border-radius:0 8px 8px 0;background:var(--attention);color:var(--attention-text)";
  var ageTimer = null;
  function ageStrip(summary, weekly) {
    var p = el("p", {id: "gl-data-age"});
    function draw() { var a = dataAge(summary, weekly, Date.now()); p.textContent = a.text; p.setAttribute("style", a.stale ? AGE_STALE : AGE_STYLE); }
    draw();
    if (ageTimer) clearInterval(ageTimer);
    ageTimer = setInterval(draw, 60000); /* the relative time, and a kickoff passing, while the tab stays open */
    return p;
  }

  /* ---------- header ---------- */
  function renderHeader(plan) {
    var lg = plan.league || {}, me = plan.me || {}, sim = plan.sim || {}, wins = plan.wins || {}, box = el("section", {"aria-labelledby": "gl-title"});
    box.appendChild(el("p", {class: "eyebrow", text: [lg.name, lg.season, isNum(lg.current_week) ? "Week " + lg.current_week : null, MOCK ? "Sample data" : null].filter(Boolean).join(" · ")}));
    box.appendChild(el("h1", {id: "gl-title", text: "Games left"}));
    var rank = ordinal(me.rank);
    box.appendChild(el("p", {class: "gl-record"}, el("strong", {text: me.name || "Your team"}), " · ", record(me) || na("Record not read from the league"), " · ",
      rank ? rank + (isNum(lg.num_teams) ? " of " + lg.num_teams : "") : na("Rank not read from the league"),
      " · ", el("a", {href: "./", text: "Change league"})));
    if ((plan.need || []).length) {
      var need = el("div", {class: "gl-need"});
      plan.need.forEach(function (s) { need.appendChild(el("p", {text: s})); });
      box.appendChild(need);
    }

    var facts = el("dl", {class: "gl-facts"});
    function fact(label, value, sub) { facts.appendChild(el("div", {}, el("dt", {text: label}), el("dd", {}, value, sub ? el("small", {text: sub}) : null))); }
    fact("Make the playoffs", pct(sim.playoff_p, "The season has not been simulated"), isNum(lg.playoff_teams) ? "Top " + lg.playoff_teams + " get in" : null);
    fact("Expected seed", one(sim.expected_seed, "The season has not been simulated"), null);
    fact("Top seed", pct(sim.top_seed_p, "The season has not been simulated"), null);
    if (sim.bye_p != null) fact("First-round bye", pct(sim.bye_p), null);
    fact("Expected wins", one(wins.expected, "No win chances yet"), isNum(wins.games) ? "of " + wins.games + " left" : null);
    box.appendChild(facts);

    var top = el("div", {class: "gl-top"});
    var goals = el("section", {class: "card", "aria-labelledby": "gl-goals-t"}, el("h2", {id: "gl-goals-t", text: "What you're playing for"}));
    var gl = el("ul", {class: "gl-goals"});
    (plan.goals || []).forEach(function (g) { gl.appendChild(el("li", {}, el("b", {class: "gchip goal-label", text: g.label || GOAL_SHORT[g.id] || g.id}), el("span", {text: g.detail || ""}))); });
    goals.appendChild(gl);
    top.appendChild(goals);

    var dist = el("section", {class: "card", "aria-labelledby": "gl-wins-t"}, el("h2", {id: "gl-wins-t", text: "Wins from the games left"}));
    var rows = el("div", {class: "gl-dist"}), byFinal = {};
    (sim.by_final_wins || []).forEach(function (b) { byFinal[b.wins] = b; });
    (wins.dist || []).forEach(function (d) {
      var fin = isNum(me.wins) && isNum(me.losses) && isNum(wins.games) ? (me.wins + d.wins) + "-" + (me.losses + wins.games - d.wins) + (me.ties ? "-" + me.ties : "") : null;
      var reach = isNum(me.wins) ? byFinal[me.wins + d.wins] : null;
      var sub = [fin ? "finish " + fin : null, reach && isNum(reach.playoff_p) ? "playoffs " + pctText(reach.playoff_p) : null].filter(Boolean).join(" · ");
      rows.appendChild(el("div", {class: "lab"}, d.wins + (d.wins === 1 ? " win" : " wins"), sub ? el("small", {text: sub}) : null));
      rows.appendChild(el("div", {class: "track", "aria-hidden": "true"}, el("i", {class: "fill", style: "width:" + (isNum(d.p) ? Math.max(0, Math.min(100, d.p * 100)).toFixed(1) : 0) + "%"})));
      rows.appendChild(el("div", {class: "val"}, pct(d.p)));
    });
    dist.appendChild(rows);
    var clinch = [];
    /* clinch_wins and safe_wins are final win totals for the season, not wins still needed. */
    function more(total) { return isNum(me.wins) ? " (" + Math.max(0, total - me.wins) + " more)" : ""; }
    if (isNum(sim.clinch_wins)) clinch.push("Clinch: " + sim.clinch_wins + " wins" + more(sim.clinch_wins) + " puts you in whatever else happens.");
    if (isNum(sim.safe_wins)) clinch.push("Safe: " + sim.safe_wins + " wins" + more(sim.safe_wins) + " gets you in at least 95% of the time.");
    if (clinch.length) dist.appendChild(el("p", {class: "fine", text: clinch.join(" ")}));
    var sp = plan.spread || {};
    var basis = [isNum(sp.sd) ? "Weekly spread: " + sp.sd.toFixed(1) + " points per team" + (sp.basis ? " (" + sp.basis + ")." : ".") : (sp.basis || null), isNum(sim.runs) ? "Playoff odds and seeds from " + sim.runs.toLocaleString() + " simulated seasons." : null,
      "Win counts use the DDF win chance for each game, counted on its own."].filter(Boolean).join(" ");
    dist.appendChild(el("p", {class: "fine", text: basis}));
    top.appendChild(dist);
    box.appendChild(top);
    return box;
  }

  /* ---------- one lineup ---------- */
  function playerRow(p, slot) {
    var meta = [p.pos, p.nfl_team].filter(Boolean).join(" · ");
    var who = el("td", {class: "who"}, el("b", {text: p.name || "Unknown player"}), p.status ? el("span", {class: "st", text: p.status}) : null,
      el("small", {}, meta, p.source ? el("span", {class: "src" + (p.rescored === false ? " src-default" : ""), title: p.source_label || "Projection source", text: p.source_tag || SOURCES[p.source] || p.source}) : null));
    var pts;
    if (p.bye) pts = el("span", {class: "st bye", text: "BYE"});
    else if (isNum(p.points)) pts = p.points.toFixed(1);
    else pts = na(p.note || "No projection this week");
    if (p.note) who.appendChild(el("small", {class: !p.bye && !isNum(p.points) ? "why" : "", text: p.note}));
    else if (!p.bye && !isNum(p.points)) who.appendChild(el("small", {class: "why", text: "No projection this week"}));
    return el("tr", {}, el("td", {class: "slot", text: slot || p.slot || "BN"}), who, el("td", {class: "pts"}, pts));
  }
  function lineupTable(rows, caption) {
    return el("table", {}, el("caption", {class: "sr", text: caption}),
      el("thead", {}, el("tr", {}, el("th", {scope: "col", text: "Slot"}), el("th", {scope: "col", text: "Player"}), el("th", {scope: "col", class: "pts", text: "Pts"}))), rows);
  }
  function renderLineup(lu, title, noneText) {
    var box = el("div", {class: "gl-lu"});
    if (!lu) { box.appendChild(el("div", {class: "gl-lu-head"}, el("h3", {text: title}))); box.appendChild(el("p", {class: "gl-lu-none", text: noneText})); return box; }
    box.appendChild(el("div", {class: "gl-lu-head"}, el("h3", {text: lu.name || title}), el("span", {class: "tot"}, one(lu.total, "No lineup total: no projections for these starters"))));
    /* the live week: the total is the score so far plus the best lineup still to play */
    if (lu.live && isNum(lu.banked)) box.appendChild(el("p", {class: "gl-lu-none", text: "Score so far " + lu.banked.toFixed(1) + (isNum(lu.still_to_come) ? " + " + lu.still_to_come.toFixed(1) + " still to play" : "")}));
    var body = el("tbody");
    (lu.starters || []).forEach(function (p) { body.appendChild(playerRow(p)); });
    (lu.empty_slots || []).forEach(function (s) {
      body.appendChild(el("tr", {class: "empty"}, el("td", {class: "slot", text: s}), el("td", {class: "who"}, "Empty", el("small", {class: "why", text: "No player to start in this slot"})), el("td", {class: "pts"}, na("Empty slot: nothing is counted for it"))));
    });
    var t = lineupTable(body, "Best lineup, " + (lu.name || title)); box.appendChild(t);
    if ((lu.unscored || []).length) {
      var ul = el("ul", {class: "unscored"}, el("b", {text: "Not scored, so not in the total"}));
      lu.unscored.forEach(function (u) { ul.appendChild(el("li", {text: (u.name || "Unknown player") + (u.reason ? ": " + u.reason : "")})); });
      box.appendChild(ul);
    }
    if ((lu.bench || []).length) {
      var bb = el("tbody");
      lu.bench.forEach(function (p) { bb.appendChild(playerRow(p, "BN")); });
      var bt = lineupTable(bb, "Bench, " + (lu.name || title));
      box.appendChild(el("details", {}, el("summary", {text: "Bench (" + lu.bench.length + ")"}), bt));
    }
    return box;
  }

  /* ---------- games ---------- */
  function renderGames(plan) {
    var goalLabel = {};
    (plan.goals || []).forEach(function (g) { goalLabel[g.id] = GOAL_SHORT[g.id] || g.label || g.id; });
    var sec = el("section", {"aria-labelledby": "gl-games-t"}, el("h2", {id: "gl-games-t", text: "Game by game"}),
      el("p", {class: "muted", text: "Each side's total is its best legal lineup on this week's projections. Tap a game to see both lineups."}),
      plan.win_note ? el("p", {class: "fine gl-how", text: plan.win_note}) : null);
    var table = el("table", {class: "gl-games"}, el("thead", {}, el("tr", {},
      el("th", {scope: "col", text: "Wk"}), el("th", {scope: "col", text: "Opponent"}), el("th", {scope: "col", text: "You – them"}), el("th", {scope: "col", text: "Win chance"}),
      el("th", {scope: "col", text: "Game"}), el("th", {scope: "col", text: "Moves"}), el("th", {scope: "col"}, el("span", {class: "sr", text: "Lineups"})))));
    [["regular", "Regular season"], ["playoffs", "Playoffs"]].forEach(function (ph) {
      var games = (plan.games || []).filter(function (g) { return (g.phase || "regular") === ph[0]; });
      if (!games.length) return;
      var body = el("tbody");
      body.appendChild(el("tr", {class: "phase"}, el("th", {colspan: "7", scope: "rowgroup", text: ph[1]})));
      games.forEach(function (g) { gameRows(plan, g, goalLabel).forEach(function (r) { body.appendChild(r); }); });
      table.appendChild(body);
    });
    sec.appendChild(el("div", {class: "gl-games-wrap"}, table));
    if (!(plan.games || []).length) sec.appendChild(el("p", {class: "empty", text: "No games left on the schedule."}));
    return sec;
  }
  function gameRows(plan, g, goalLabel) {
    var id = "gl-wk-" + g.week, why = missingFor(plan, g.week), lab = function (t) { return el("span", {class: "cell-label", text: t}); };
    var win = g.win || {}, hs = g.high_score, opp = g.opp;

    var oppCell = el("td", {class: "opp"});
    if (opp) {
      oppCell.appendChild(el("b", {text: opp.name || "Opponent"}));
      var bits = [record(opp), ordinal(opp.rank), isNum(opp.playoff_p) ? "playoffs " + pctText(opp.playoff_p) : null].filter(Boolean);
      oppCell.appendChild(el("small", {text: bits.join(" · ")}));
    } else {
      oppCell.appendChild(el("b", {text: g.phase === "playoffs" ? "Playoff opponent to be set" : "Opponent to be set"}));
      if (g.opp_note) oppCell.appendChild(el("small", {text: g.opp_note}));
    }
    if (opp && g.opp_note) oppCell.appendChild(el("small", {text: g.opp_note}));
    if (!opp && (g.likely || []).length) oppCell.appendChild(el("small", {text: "Likely: " + g.likely.map(function (l) {
      return (l.name || "Unknown team") + (isNum(l.p) ? " " + pctText(l.p) : "") + (isNum(l.total) ? " (" + l.total.toFixed(1) + ")" : "");
    }).join(", ")}));
    if (g.status && !/^(upcoming|scheduled|pre|preevent|not_started)$/i.test(g.status)) oppCell.appendChild(el("small", {class: "mono", text: STATUS[String(g.status).toLowerCase()] || String(g.status).replace(/_/g, " ")}));

    var theirsWhy = g.theirs ? "No lineup total: no projections for their starters" : (why || "The opponent is not known yet");
    var line = el("td", {class: "line"}, lab("You – them"),
      el("span", {class: "pair"}, one(g.mine && g.mine.total, "No lineup total for your team"), el("span", {class: "them"}, " – ", one(g.theirs && g.theirs.total, theirsWhy))),
      isNum(g.margin) ? el("small", {class: "mono", text: signed(g.margin) + " on lineups"}) : null);

    var winCell = el("td", {class: "win"}, lab("Win chance"),
      el("div", {class: "big"}, pct(win.ddf, g.theirs ? "No DDF win chance for this game" : "No DDF win chance until the opponent is known")),
      el("small", {text: "Sim · from weekly projections"}),
      /* Yahoo's number for the current week only (Jeremy, 2026-11-27): later weeks it projects lineups as they sit today */
      g.week === plan.league.current_week ? el("div", {class: "yh"}, el("b", {}, pct(win.yahoo, why || "Yahoo has no win chance for this game yet")), " Yahoo's number") : null);
    var st0 = g.stake || {};
    var labelCell = el("td", {class: "typ"}, lab("Game"),
      g.type ? el("span", {class: "type " + (TYPES[g.type] ? g.type : "free"), text: TYPES[g.type] || g.type}) : null,
      st0.text ? el("small", {class: "stake", title: (st0.unpriced || []).length ? "Payouts not set yet (" + st0.unpriced.join(", ").replace(/_/g, " ") + ") count as points of title odds: 1 = one point of title chance, best record = 20." : "", text: st0.text}) : null);

    /* goals live in the header (Jeremy, 2026-11-27); the week's high-score chance moves to the opened row */
    var hsLine = el("span", {}, "Weekly high score: ", hs ? pct(hs.chance, "No high-score chance for this week") : na("No high-score chance for this week"));
    if (hs && isNum(hs.my_rank)) hsLine.appendChild(document.createTextNode(" · you project " + ordinal(hs.my_rank) + (isNum(hs.of) ? " of " + hs.of : "")));
    if (hs && isNum(hs.expected_dollars)) hsLine.appendChild(document.createTextNode(" · worth $" + hs.expected_dollars.toFixed(2) + " expected"));

    var movesCell = el("td", {class: "moves" + ((g.moves || []).length ? "" : " none")});
    if ((g.moves || []).length) {
      var ul = el("ul");
      g.moves.forEach(function (m) {
        var li = el("li", {}, el("span", {class: "kind", text: KINDS[m.kind] || m.kind || "Move"}), m.text || "");
        if (isNum(m.gain)) { li.appendChild(document.createTextNode(" ")); li.appendChild(el("span", {class: "gain" + (m.gain < 0 ? " neg" : ""), text: signed(m.gain)})); }
        if (m.when) { var w = when(m.when); li.appendChild(el("small", {text: /^\d{4}-\d\d-\d\d/.test(m.when) ? "By " + w : w.charAt(0).toUpperCase() + w.slice(1)})); }
        ul.appendChild(li);
      });
      movesCell.appendChild(lab("Moves for this game")); movesCell.appendChild(ul);
    } else movesCell.appendChild(el("span", {class: "muted", text: "None"}));

    var btn = el("button", {type: "button", class: "gl-toggle", "aria-expanded": "false", "aria-controls": id}, el("span", {class: "lbl", text: "Show both lineups, week " + g.week}));
    var row = el("tr", {class: "game"},
      el("td", {class: "wk"}, el("small", {text: "Wk"}), String(g.week)), oppCell, line, winCell,
      labelCell, movesCell, el("td", {class: "tog"}, btn));

    var facts = el("p", {class: "gl-detail-facts"}, hsLine);
    if (hs && hs.top) facts.appendChild(el("span", {}, "Projected top score: ", el("b", {text: (hs.top.name || "—") + " "}), el("b", {class: "mono"}, one(hs.top.total))));
    if (g.yahoo_proj) facts.appendChild(el("span", {}, "Yahoo projects ", el("b", {class: "mono"}, one(g.yahoo_proj.mine), " – ", one(g.yahoo_proj.theirs))));
    var st = g.stake || {};
    var pts = function (dp) { return (dp > 0 ? "+" : dp < 0 ? "−" : "") + Math.abs(Math.round(dp * 100)) + " pts"; };
    var stakes = [isNum(st.playoffs) ? "playoff odds " + pts(st.playoffs) : null, isNum(st.seed) ? (st.seed_basis || "seed") + " odds " + pts(st.seed) : null,
      isNum(st.top_seed) && st.seed_basis !== "1st seed" ? "1st seed odds " + pts(st.top_seed) : null].filter(Boolean);
    if (stakes.length) facts.appendChild(el("span", {}, "A win instead of a loss: ", el("b", {text: stakes.join(", ")})));
    var detail = el("tr", {class: "detail", id: id, hidden: ""}, el("td", {colspan: "7"}, facts.childNodes.length ? facts : null,
      el("div", {class: "gl-lineups"}, renderLineup(g.mine, "Your lineup", "No lineup for your team this week."),
        renderLineup(g.theirs, opp ? opp.name : "Their lineup", g.opp_note || "The opponent is not known yet, so there is no lineup to show."))));

    function toggle() {
      var open = detail.hidden;
      detail.hidden = !open; row.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open));
      btn.firstChild.textContent = (open ? "Hide" : "Show") + " both lineups, week " + g.week;
    }
    row.addEventListener("click", function (e) { if (e.target.closest("a,summary,.na") && !e.target.closest(".gl-toggle")) return; toggle(); });
    return [row, detail];
  }

  /* ---------- provenance ---------- */
  function renderFooter(plan, flaim) {
    var sec = el("section", {class: "card gl-prov", "aria-labelledby": "gl-prov-t"}, el("h2", {id: "gl-prov-t", text: "Where these numbers come from"}));
    if ((plan.sources || []).length) {
      var s = el("ul");
      plan.sources.forEach(function (x) { s.appendChild(el("li", {text: x})); });
      sec.appendChild(s);
    }
    if ((plan.missing || []).length) {
      sec.appendChild(el("h3", {text: "Not available"}));
      var m = el("ul");
      plan.missing.forEach(function (x) { m.appendChild(el("li", {}, el("b", {text: x.what || "Unknown"}), x.reason ? ": " + x.reason : "")); });
      sec.appendChild(m);
      sec.appendChild(el("p", {class: "fine", text: "A dash (—) means the number is missing, not zero. Nothing is counted for it."}));
    }
    var pulled = plan.league && plan.league.pulled_at;
    if (flaim) sec.appendChild(el("p", {class: "flaim", text: "League data via Flaim · pulled " + (pulled ? whenFull(pulled) : "time not recorded")}));
    return sec;
  }

  function render(plan, flaim, summary, weekly) {
    var root = $("gl-root");
    root.textContent = "";
    var head = renderHeader(plan);
    if (summary) head.insertBefore(ageStrip(summary, weekly), head.querySelector(".gl-record").nextSibling); /* under the record line */
    root.appendChild(head);
    root.appendChild(renderGames(plan));
    root.appendChild(renderFooter(plan, flaim));
    if (plan.league && plan.league.name) $("ctx-league").textContent = "My league · " + plan.league.name;
    $("gl-status").textContent = "";
    root.hidden = false;
    /* ?open=<week> opens that game's lineups (a link from another page can point at one game). */
    var openBtn = QS.get("open") && document.querySelector('.gl-toggle[aria-controls="gl-wk-' + String(QS.get("open")).replace(/\D/g, "") + '"]');
    if (openBtn) openBtn.click();
  }
  function status(node, kind) {
    var s = $("gl-status");
    s.textContent = "";
    s.appendChild(el("div", {class: kind === "err" ? "attention" : "card"}, node));
    $("gl-root").hidden = true;
  }
  function addLeagueLine(lead) { return el("p", {}, lead + " ", el("a", {href: "./", text: "Add your league"}), "."); }

  /* ---------- boot ---------- */
  var more = $("gl-more");
  more.querySelector("button").addEventListener("click", function () { var open = more.classList.toggle("open"); this.setAttribute("aria-expanded", String(open)); });
  document.addEventListener("click", function (e) { if (!more.contains(e.target)) { more.classList.remove("open"); more.querySelector("button").setAttribute("aria-expanded", "false"); } });

  async function boot() {
    if (MOCK) {
      var r = await fetch(MOCK_URL);
      if (!r.ok) throw new Error("Sample plan not found at " + MOCK_URL + ". Serve the staging folder, not staging/account.");
      var sample = await r.json();
      render(sample, !!(sample._mock && sample._mock.source_kind === "flaim"));
      return;
    }
    if (!window.supabase) throw new Error("Sign-in did not load. Check your connection and reload.");
    /* Same session as the Add your league page: this tab's sessionStorage. */
    sb = window.supabase.createClient(SUPABASE_URL, PUBLISHABLE_KEY, {auth: {flowType: "implicit", detectSessionInUrl: true, persistSession: true, storage: window.sessionStorage}});
    var session = (await sb.auth.getSession()).data.session;
    if (!session) { status(addLeagueLine("Sign in to see your games left.")); return; }
    var want = QS.get("league"), id = want;
    if (!id) {
      var me = await api("GET", "/me");
      var first = (me.leagues || []).filter(function (l) { return l.my_team_key; })[0];
      if (!first) { status(addLeagueLine((me.leagues || []).length ? "Pick your team in your league first." : "No league yet.")); return; }
      id = first.id;
    }
    var got = await Promise.all([api("GET", "/leagues/" + encodeURIComponent(id)), api("GET", "/leagues/" + encodeURIComponent(id) + "/weekly")]);
    var league = got[0].league, weekly = got[1].weekly || got[1];
    if (!league || !league.summary) throw new Error("This league has not been read yet. Open it on the Add your league page and press Refresh now.");
    if (!league.my_team_key) { status(addLeagueLine("Pick your team in this league first.")); return; }
    if (!window.DDFWeekly || typeof window.DDFWeekly.plan !== "function") throw new Error("The planner did not load. Reload the page.");
    /* The team picked on the Add your league page lives on the league row; the planner falls back to the summary's own. */
    /* the staging Team / Find / Build links stay on this league */
    Array.prototype.forEach.call(document.querySelectorAll('header a[href="team.html"], header a[href="find.html"], header a[href="build.html"], header a[href="games-left.html"]'), function (a) { a.href = a.getAttribute("href") + "?league=" + encodeURIComponent(id); });
    var plan = window.DDFWeekly.plan(league.summary, weekly, league.my_team_key ? {myTeamKey: league.my_team_key} : {});
    render(plan, !!(league.summary.source && league.summary.source.kind === "flaim"), league.summary, weekly);
  }
  boot().catch(function (err) { status(el("p", {text: err.message || String(err)}), "err"); });
})();
