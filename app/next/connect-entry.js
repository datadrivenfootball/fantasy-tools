/* connect.html on the live engine (JEG-1538): read the pasted rosters, show what we read, keep the league for setup.
 *
 * - "Check my rosters" (or a paste) reads the box with DDF.leaguePaste (live roster-paste.js matcher on engine rows,
 *   team names from rosterparse.js) and fills "Here's what we read from your paste" from that result.
 * - A paste we cannot read shows a status line and the edit-names box: the reader types the team names and we read again.
 * - One team's page shows the existing "That looks like one team" notice.
 * - Manual entry: team names, then players found by name on the engine's player list.
 * - The league is kept in sessionStorage ddf:pasted (league-paste.js record(), setup.html adds `me`); a new paste or
 *   manual league clears a league carried from a chat link (DDF.link.clear()), so the two never mix.
 * - Device: the page shows phone or computer copy steps (html[data-device]); "On a phone" / "On a computer" switches.
 *   Detection is local only (media queries, then the user agent); when unsure, both versions show.
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var plural = function (n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); };

  /* ---------- device ---------- */
  function detectDevice() {
    try {
      var coarse = matchMedia("(pointer: coarse)").matches, narrow = matchMedia("(max-width: 760px)").matches;
      var phoneUa = /iPhone|iPod|Android.+Mobile|Windows Phone|Mobile Safari/i.test(navigator.userAgent || "");
      if (phoneUa || (coarse && narrow)) return "phone";
      if (!coarse) return "desktop";
    } catch (e) { /* unknown: show both */ }
    return "";
  }
  function setDevice(d) {
    if (d) document.documentElement.setAttribute("data-device", d); else document.documentElement.removeAttribute("data-device");
  }
  setDevice(detectDevice());
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-show-device]");
    if (b) { e.preventDefault(); setDevice(b.getAttribute("data-show-device")); }
  });

  /* ---------- engine rows and the player table ---------- */
  var rowsCache = null;
  function rows() {
    if (rowsCache) return rowsCache;
    var C = DDF.engine && DDF.engine.controls && DDF.engine.controls();
    if (!C || !C.getAllRows) return null;
    rowsCache = C.getAllRows().filter(function (r) { return r && r.name && r.player_key !== undefined && r.player_key !== null; })
      .map(function (r) { return {player_key: r.player_key, name: r.name, pos: r.pos || "", team: r.team || ""}; });
    return rowsCache;
  }
  function table() { try { return (DDF.link && DDF.link.table && DDF.link.table(1)) || []; } catch (e) { return []; } }
  function whenRows() {
    var r = rows();
    if (r) return Promise.resolve(r);
    if (!DDF.engine || !DDF.engine.ready) return Promise.reject(new Error("engine"));
    return DDF.engine.ready.then(function () { var x = rows(); if (!x) throw new Error("engine"); return x; });
  }

  /* ---------- the kept league ---------- */
  /* Editing (connect.html?edit=1 from "Edit league", JEG-1568): the current league stays in use until a new paste is read
     or rosters are entered. `editprev` keeps what it was (sessionStorage ddf:editprev, for setup's name and team prefill);
     backing out or emptying the box puts it back. A chat league's settings are saved to the engine when it is replaced,
     so settings.html still shows them. */
  var editing = null;
  function startEditing() {
    if (!/[?&]edit=1(&|$)/.test(location.search) || !DDF.leagueMeta) return null;
    var info = DDF.leagueMeta.info();
    if (!info) return null;
    var raw = function (k) { try { return sessionStorage.getItem("ddf:" + k); } catch (e) { return null; } };
    var settings = null;
    try { settings = DDF.link && DDF.link.settings ? DDF.link.settings() : null; } catch (e) { settings = null; }
    var snap = {pasted: raw("pasted"), league: raw("league"), link: raw("link"), name: info.named ? info.name : null,
      team: info.team || null, source: info.source, settings: settings};
    DDF.state.set("editprev", {name: snap.name, team: snap.team, source: snap.source});
    return snap;
  }
  function restoreEditing() {
    ["pasted", "league", "link"].forEach(function (k) {
      try { if (editing[k] === null) sessionStorage.removeItem("ddf:" + k); else sessionStorage.setItem("ddf:" + k, editing[k]); } catch (e) { /* storage blocked */ }
    });
    document.dispatchEvent(new CustomEvent("ddf:pasted", {detail: kept()}));
  }
  function keepChatSettings() {
    var st = editing && editing.settings;
    if (!st || !DDF.engine || !DDF.engine.apply || !Array.isArray(st.slots)) return;
    try {
      DDF.engine.apply({scoring: st.scoring, teams: st.teams, superflex: !!st.superflex,
        superflexSlots: DDF.link && DDF.link.superflexSlots ? DDF.link.superflexSlots(st) : (st.superflex ? 1 : 0),
        roster: Object.assign({QB: st.slots[0], RB: st.slots[1], WR: st.slots[2], TE: st.slots[3], FLEX: st.slots[4], BENCH: st.slots[5]},
          DDF.link && DDF.link.kdefSlots ? DDF.link.kdefSlots(st) : {})});   /* JEG-1632: K and DEF slots */
    } catch (e) { /* settings.html asks again */ }
  }
  // JEG-1689 (was JEG-1571's QB flex count alone): the settings a paste shows (league-paste.js inferSettings: team count,
  // lineup slots, bench, K and DEF) go to the engine, except a field the reader already confirmed or changed on
  // settings.html for this league. settings.html marks each one "From your paste" for the reader to check.
  function pastedSettings(record) {
    var patch = record && DDF.leaguePaste.enginePatch(record.pasteSettings, record.confirmed);
    if (!patch || !DDF.engine || !DDF.engine.apply) return;
    try { DDF.engine.apply(patch); } catch (e) { /* settings.html asks */ }
  }
  /* the same league read again keeps what the reader confirmed on settings.html (editing the box drops the kept league
     first, so the last one dropped on this page counts too) */
  var dropped = null;
  function withConfirmed(record) {
    var prior = kept() || dropped;
    if (record && record.pasteSettings && prior && prior.confirmed && DDF.leaguePaste.sameLeague(prior, record)) record.confirmed = prior.confirmed;
    return record;
  }
  function save(record) {
    if (pickable(record) && !Number.isInteger(record.me)) {
      var known = knownTeam(record, kept() || dropped);
      if (known !== null) { record.me = known; record.own = known; }
    }
    if (needsScoring(record) && !record.scoring) {
      var before = kept() || dropped;
      if (before && before.scoring && DDF.leaguePaste.sameLeague(before, record)) record.scoring = before.scoring;
      else if (editing && editing.source !== "link") { try { record.scoring = DDF.engine.settings().scoring || null; } catch (e) { /* asked on the card */ } }
    }
    if (editing && editing.source === "link") keepChatSettings();
    try { if (DDF.link && DDF.link.clear) DDF.link.clear(); } catch (e) { /* no chat league to clear */ }
    DDF.state.set("pasted", record);
    /* JEG-1548: the method only (paste, sleeper, manual); analytics.js drops anything not on its list */
    if (DDF.track && record && typeof record.source === "string") DDF.track("league-added/" + record.source);
    drawScoring(record);   /* before ddf:pasted: connect.html's Next reads the scoring on that event */
    document.dispatchEvent(new CustomEvent("ddf:pasted", {detail: record}));
    drawTeamPick(record);
    if (Number.isInteger(record.me) && pickable(record)) pickTeam(record.me, {quiet: true});
  }
  function drop() {
    if (editing) { restoreEditing(); return; }
    dropped = kept() || dropped;
    DDF.state.remove("pasted");
    document.dispatchEvent(new CustomEvent("ddf:pasted", {detail: null}));
  }
  function kept() { var p = DDF.state.get("pasted", null); return p && Array.isArray(p.teams) ? p : null; }

  /* ---------- status line under the paste box ---------- */
  function status(text, kind) {
    var st = $("entry-status");
    if (!st) return;
    st.textContent = text || "";
    st.className = "notice" + (kind ? " " + kind : "");
  }

  /* ---------- "Here's what we read from your paste" ---------- */
  var STATUS = {
    look: ['<span class="badge recognition-attention">Needs a look</span>', "More than one player fits. Check the spelling, or leave this line out."],
    missing: ['<span class="badge recognition-attention">Not found</span>', "No player found. Edit or leave this line out."],
    kdef: ['<span class="badge">Not evaluated</span>', "Kickers and defenses are not evaluated for trades."]
  };
  function teamRows(t) {
    var out = t.players.map(function (p) {
      var what = esc(p.name) + (p.pos ? " · " + esc(p.pos) : "") + (p.team ? " · " + esc(p.team) : "");
      return "<tr><td>" + esc(p.line || p.name) + '</td><td><span class="badge recognition-ok">Matched</span></td><td>' + what + "</td></tr>";
    });
    t.unmatched.forEach(function (u) {
      var s = STATUS[u.reason] || STATUS.missing, what = s[1];
      /* the players a line could be, each with its position, so the reader picks one (none is chosen for them) */
      var options = (u.options || []).map(function (o) { return esc(o.name) + (o.pos ? " · " + esc(o.pos) : "") + (o.team ? " · " + esc(o.team) : ""); });
      if (options.length) what = u.reason === "look" ? "Could be " + options.join("; ") + ". " + what
        : "Fits only a player at another position: " + options.join("; ") + ". Edit or leave this line out.";
      if (u.reason === "kdef") what = (u.pos === "K" ? "Kicker" : "Defense") + (u.team ? " · " + esc(u.team) : "") + ". " + what;
      out.push("<tr><td>" + esc(u.line) + "</td><td>" + s[0] + "</td><td>" + what + "</td></tr>");
    });
    return out.join("") || '<tr><td colspan="3">No players read for this team yet.</td></tr>';
  }
  function summaryText(res) {
    var head = "Found " + plural(res.teams.length, "team") + " and " + plural(res.matched, "player") + ".";
    var issues = [];
    if (res.look) issues.push(res.look + " need" + (res.look === 1 ? "s" : "") + " a look");
    if (res.missing) issues.push(res.missing + " not found");
    if (res.notEvaluated) issues.push(res.notEvaluated + " kicker or defense line" + (res.notEvaluated === 1 ? "" : "s") + " not evaluated");
    return head + (issues.length ? " " + issues.join(", ").replace(/^./, function (c) { return c.toUpperCase(); }) + "." : "");
  }
  function showResult(res, from) {
    var card = $("recognized");
    /* a Sleeper or ESPN league is read from the platform, not a paste: its team names come from the league, so no rename box */
    var platformName = {sleeper: "Sleeper", espn: "ESPN"}[from];
    $("recognition-title").textContent = platformName ? "Here's what we read from " + platformName : "Here's what we read from your paste";
    $("edit-team-names").hidden = !!platformName;
    $("recognition-summary").textContent = summaryText(res);
    var lg = res.league || {}, found = $("recognition-league");
    if (found) {
      found.textContent = lg.leagueName ? "We found: " + lg.leagueName + (lg.leagueId ? " · ID# " + lg.leagueId : "") + ". You can confirm or change the name on the next step." : "";
      found.hidden = !lg.leagueName;
    }
    $("recognition-teams").innerHTML = res.teams.map(function (t, i) {
      var issues = t.unmatched.filter(function (u) { return u.reason !== "kdef"; }).length;
      var label = esc(t.name) + " · " + plural(t.players.length, "player") + " matched" + (issues ? " · " + issues + " to check" : "");
      return '<details class="recognition-team"' + (issues || res.teams.length <= 2 ? " open" : "") + "><summary>" + label + "</summary>"
        + '<div class="table-wrap"><table><caption class="sr-only">Pasted lines for ' + esc(t.name) + " and what we matched</caption>"
        + '<thead><tr><th scope="col">Pasted line</th><th scope="col">Status</th><th scope="col">What we matched</th></tr></thead><tbody>'
        + teamRows(t) + "</tbody></table></div></details>";
    }).join("");
    var partial = $("recognition-partial");
    if (partial) partial.hidden = !(res.look || res.missing);
    card.hidden = false;
    $("recognize-button").setAttribute("aria-expanded", "true");
  }
  function hideResult() {
    var card = $("recognized");
    if (card) card.hidden = true;
    var b = $("recognize-button"); if (b) b.setAttribute("aria-expanded", "false");
  }

  /* ---------- "Which team is yours?" on the read card ----------
     The card already lists every team, so the reader picks theirs here and Next goes straight to League settings; the
     team page (setup.html) stays for switching later and is still where Next goes before a team is picked. Preselected
     when the team is known: editing a league (the team you had, by name) or reading the same league again. */
  var askReplace = false;
  function pickable(rec) { return !!rec && (rec.source === "paste" || rec.source === "sleeper" || rec.source === "espn") && Array.isArray(rec.teams) && rec.teams.length > 1; }
  function knownTeam(rec, prior) {
    var names = rec.teams.map(function (t) { return t.name; }), want = null;
    var prev = DDF.state.get("editprev", null);
    if (prev && prev.team) want = prev.team;
    else if (prior && Number.isInteger(prior.me) && prior.teams[prior.me] && DDF.leaguePaste.sameLeague(prior, rec)) want = prior.teams[prior.me].name;
    var at = want === null ? -1 : names.indexOf(want);
    return at >= 0 ? at : null;
  }
  function teamLine(t) {
    var n = (t.players || []).length, top = (t.players || []).slice(0, 2).map(function (p) { return p.name; });
    return plural(n, "player") + " matched" + (top.length ? " · " + top.join(", ") : "");
  }
  function drawTeamPick(rec) {
    var box = $("team-pick"), list = $("team-pick-list");
    if (!box || !list) return;
    box.hidden = !pickable(rec);
    if (box.hidden) { list.innerHTML = ""; return; }
    list.innerHTML = rec.teams.map(function (t, i) {
      var on = rec.me === i;
      return '<label class="team-pick-option' + (on ? " selected" : "") + '"><input type="radio" name="team-pick" value="' + i + '"' + (on ? " checked" : "")
        + '><span class="team-pick-text"><strong>' + esc(t.name) + "</strong><small>" + esc(teamLine(t)) + "</small></span></label>";
    }).join("");
  }
  /* Picking only marks the team in this tab's league (ddf:pasted me/own). The saved league (ddf.v2.workspaces) and
     Viewing as are written on Next (confirmTeam), as on main where they wait for the team page: until then "Keep my
     league" puts everything back. */
  function pickTeam(i, opts) {
    var rec = kept();
    if (!pickable(rec) || !rec.teams[i]) return;
    rec.me = i; rec.own = i; DDF.state.set("pasted", rec);
    if (!(opts && opts.quiet) && DDF.leagueMeta) DDF.leagueMeta.want("team", i + ":" + rec.teams[i].name);
    /* another saved league is replaced only after the reader says so, on setup.html (a dry run: nothing written) */
    var prev = DDF.state.get("editprev", null);
    var r = DDF.setupEntry && DDF.setupEntry.bridge ? DDF.setupEntry.bridge(rec, {dryRun: true, replace: !!prev}) : "failed";
    askReplace = r === "ask" && !DDF.state.get("bridgeKeep", false);
    Array.prototype.forEach.call(document.querySelectorAll("#team-pick-list .team-pick-option"), function (l, k) { l.classList.toggle("selected", k === i); });
    document.dispatchEvent(new CustomEvent("ddf-teampick", {detail: {me: i, name: rec.teams[i].name, askReplace: askReplace}}));
  }
  /* only a team shown on this page's card counts: a league kept from before (editing, no new read) still confirms its
     team on setup.html */
  /* Next with a team picked on the card: what Next on setup.html does. Viewing as, the league's name (the name you had
     while editing, else the one found in the paste), the saved league, and the edit is done. */
  function confirmTeam() {
    var rec = kept(), prev = DDF.state.get("editprev", null);
    if (!pickable(rec) || !Number.isInteger(rec.me)) return;
    if (DDF.viewAs) DDF.viewAs.set(rec.me, {own: true});
    rec = kept();
    if (!rec.name) { var name = (prev && prev.name) || rec.suggestedName || null; if (name) rec.name = name; }
    DDF.state.set("pasted", rec);
    if (DDF.setupEntry && DDF.setupEntry.bridge) DDF.setupEntry.bridge(rec, prev ? {replace: true} : null);
    if (DDF.leagueMeta) DDF.leagueMeta.refresh();
    DDF.state.remove("editprev");
  }
  function teamChoice() {
    var box = $("team-pick"), card = $("recognized");
    if (!box || box.hidden || !card || card.hidden) return null;
    var rec = kept();
    return pickable(rec) && Number.isInteger(rec.me) && rec.teams[rec.me] ? {me: rec.me, name: rec.teams[rec.me].name, askReplace: askReplace} : null;
  }

  /* ---------- scoring on the read card (pasted leagues) ----------
     A rosters page never shows scoring, so a paste used to start as PPR with nothing saying it was a guess. The card
     asks PPR, Half PPR or Standard with nothing preselected, and Next waits for the answer. Preselected only when known:
     the same league read again, or the league being edited. Sleeper and chat leagues bring their own scoring.
     The answer is kept on ddf:pasted and reaches the league's settings on Next (applyPickedScoring), so "Keep my
     league" while editing leaves the league's scoring as it was. */
  function needsScoring(rec) { return !!rec && rec.source === "paste" && Array.isArray(rec.teams) && rec.teams.length > 1; }
  function applyScoring(tok) { try { if (DDF.engine && DDF.engine.apply) DDF.engine.apply({scoring: tok}); } catch (e) { /* settings.html asks */ } }
  function drawScoring(rec) {
    var box = $("scoring-pick"); if (!box) return;
    box.hidden = !needsScoring(rec);
    Array.prototype.forEach.call(box.querySelectorAll("[data-scoring]"), function (b) {
      b.setAttribute("aria-pressed", String(!box.hidden && rec.scoring === b.getAttribute("data-scoring")));
    });
  }
  function pickScoring(tok) {
    var rec = kept();
    if (!needsScoring(rec)) return;
    rec.scoring = tok; DDF.state.set("pasted", rec);
    drawScoring(rec);
    document.dispatchEvent(new CustomEvent("ddf-scoringpick", {detail: {scoring: tok}}));
  }
  function applyPickedScoring() {
    var rec = kept();
    if (needsScoring(rec) && rec.scoring && scoringChoice() !== "n/a") applyScoring(rec.scoring);
  }
  /* Settings read from the league (Sleeper, ESPN: ddf:pasted importSettings) reach the league's settings on Next, as the
     picked scoring does (#1536): while editing, reading a league changes nothing until Next, so "Keep my league" leaves
     the settings as they were. Only a league read on this page counts (the read card is showing). */
  function applyImported() {
    var rec = kept(), card = $("recognized");
    if (!rec || !rec.importSettings || !card || card.hidden || !DDF.engine || !DDF.engine.apply) return;
    if (rec.source !== "sleeper" && rec.source !== "espn") return;
    try { DDF.engine.apply(rec.importSettings); } catch (e) { /* settings.html asks */ }
  }
  /* "n/a" when the card does not ask (no read on this page, or not a paste); null until answered; else the token */
  function scoringChoice() {
    var box = $("scoring-pick"), card = $("recognized");
    if (!box || box.hidden || !card || card.hidden) return "n/a";
    var rec = kept();
    return needsScoring(rec) ? rec.scoring || null : "n/a";
  }

  /* ---------- edit-names box ---------- */
  function showEditNames(names, why) {
    var box = $("edit-names");
    $("edit-names-why").textContent = why;
    $("edit-names-input").value = (names || []).join("\n");
    $("edit-names-input").placeholder = "One team name per line";
    box.hidden = false;
  }
  function hideEditNames() { var box = $("edit-names"); if (box) box.hidden = true; }

  /* ---------- reading ---------- */
  var busy = false;
  function check(focus, scroll) {
    var text = $("rosters").value;
    var oneTeam = $("one-team-error");
    oneTeam.hidden = true;
    $("rosters").removeAttribute("aria-invalid");
    if (!text.trim()) { hideResult(); hideEditNames(); status("Paste every team's roster first.", "warn"); return Promise.resolve(null); }
    if (busy) return Promise.resolve(null);
    busy = true;
    status("Reading your rosters...", "");
    return whenRows().then(function (r) {
      busy = false;
      var res = DDF.leaguePaste.read(text, r, {table: table()});
      if (res.ok) {
        hideEditNames();
        showResult(res);
        var rec = withConfirmed(DDF.leaguePaste.record(res, "paste"));
        save(rec);
        pastedSettings(rec);
        askBookmark(res);
        status("Check the list below, then pick your team.", "ok");
        if (scroll) $("recognized").scrollIntoView({block: "start"});
        if (focus) $("recognition-title").focus({preventScroll: true});
        return res;
      }
      hideResult();
      drop();
      if (res.reason === "one-team") {
        oneTeam.hidden = false;
        $("rosters").setAttribute("aria-invalid", "true");
        status("That looks like one team's page. We need every team's roster.", "warn");
        oneTeam.scrollIntoView({block: "center"});
        return res;
      }
      status("We could not find any teams in that paste. Make sure you copied the page that lists every team's roster, then try again, or add your rosters manually.", "warn");
      showEditNames(res.names, res.names.length
        ? "We found " + plural(res.names.length, "possible team name") + ", but could not split the players by team. Fix the names so each one matches a team name in your paste, one per line."
        : "We could not find team names in your paste. If you copied the right page, type each team name as it appears there, one per line.");
      return res;
    }).catch(function () {
      busy = false;
      status("Player values are still loading. Try again in a moment.", "warn");
      return null;
    });
  }
  function readAgain() {
    if (kept() && (kept().source === "sleeper" || kept().source === "espn")) { hideEditNames(); return; }
    var names = $("edit-names-input").value.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
    if (names.length < 2) { $("edit-names-status").textContent = "Add at least two team names, one per line."; return; }
    whenRows().then(function (r) {
      var res = DDF.leaguePaste.readWithNames($("rosters").value, names, r, {table: table()});
      if (!res.ok) { $("edit-names-status").textContent = "We still could not read this paste. Enter your rosters manually instead."; return; }
      $("edit-names-status").textContent = "";
      hideEditNames();
      showResult(res);
      var rec = withConfirmed(DDF.leaguePaste.record(res, "paste"));
      save(rec);
      pastedSettings(rec);
      askBookmark(res);
      status("Check the list below, then pick your team.", "ok");
      $("recognized").scrollIntoView({block: "start"});
      $("recognition-title").focus({preventScroll: true});
    }).catch(function () { $("edit-names-status").textContent = "Player values are still loading. Try again in a moment."; });
  }
  function editNamesFromCard() {
    var p = kept();
    showEditNames(p ? p.teams.map(function (t) { return t.name; }) : [], "Fix any team name so it matches your paste, one per line, then read your rosters again.");
    $("edit-names-input").focus();
  }

  /* ---------- manual entry ---------- */
  var manual = {teams: []};
  /* a manual league keeps its picked team, name and date while it is edited here (the team by name) */
  function manualRecord() {
    var prior = kept(), mine = null;
    if (prior && prior.source === "manual" && Number.isInteger(prior.me) && prior.teams[prior.me]) {
      var at = manual.teams.map(function (t) { return t.name; }).indexOf(prior.teams[prior.me].name);
      mine = at >= 0 ? at : null;
    }
    var rec = {v: 1, source: "manual", site: "unknown", me: mine,
      enteredAt: prior && prior.source === "manual" && prior.enteredAt ? prior.enteredAt : (DDF.leagueMeta ? DDF.leagueMeta.today() : null),
      teams: manual.teams.map(function (t) { return {name: t.name, players: t.players.slice(), unmatched: []}; })};
    if (prior && prior.source === "manual" && prior.name) rec.name = prior.name;
    return rec;
  }
  var restoring = false;
  function manualSave() {
    if (restoring) return;
    /* while editing, manual rows replace the league only once two teams have players (a real league), never mid-typing */
    if (editing && manual.teams.filter(function (t) { return t.players.length; }).length < 2) { restoreEditing(); return; }
    if (manual.teams.length) save(manualRecord()); else drop();
  }
  /* JEG-1564: a roster read is a big input; the Bookmark button asks once, when it shows on a later page */
  function askBookmark(res) {
    if (!DDF.leagueMeta) return;
    DDF.leagueMeta.want("rosters", res.teams.map(function (t) { return t.name + "/" + t.players.length; }).join("|"));
  }
  function manualNames() {
    var names = $("manual-names").value.split(/\r?\n/).map(function (s) { return s.replace(/\s+/g, " ").trim().slice(0, 40); }).filter(Boolean);
    var byName = {};
    manual.teams.forEach(function (t) { byName[t.name.toLowerCase()] = t; });
    manual.teams = names.slice(0, 20).map(function (n) { return byName[n.toLowerCase()] || {name: n, players: []}; });
    var sel = $("manual-team"), was = sel.value;
    sel.innerHTML = manual.teams.map(function (t, i) { return '<option value="' + i + '">' + esc(t.name) + "</option>"; }).join("");
    if (was && manual.teams[Number(was)]) sel.value = was;
    manualRender();
    manualSave();
  }
  function manualRender() {
    var t = manual.teams[Number($("manual-team").value)] || null;
    $("manual-roster-title").textContent = t ? t.name + " · " + plural(t.players.length, "player") : "Add your team names first";
    $("manual-rows").innerHTML = t && t.players.length ? t.players.map(function (p, i) {
      return "<tr><td>" + esc(p.name) + "</td><td>" + esc(p.pos) + '</td><td><button type="button" class="link-button" data-remove="' + i + '">Remove<span class="sr-only"> ' + esc(p.name) + "</span></button></td></tr>";
    }).join("") : '<tr><td colspan="3">' + (t ? "No players yet. Find a player above and add them." : "Type each team's name above, one per line.") + "</td></tr>";
  }
  function fillPlayerOptions() {
    var r = rows();
    if (!r) return;
    $("player-options").innerHTML = r.map(function (p) { return '<option value="' + esc(p.name + " (" + p.pos + (p.team ? ", " + p.team : "") + ")") + '"></option>'; }).join("");
  }
  function manualAdd() {
    var st = $("manual-status"), t = manual.teams[Number($("manual-team").value)];
    if (!t) { st.textContent = "Add your team names first."; return; }
    var q = $("find-player").value.trim(), r = rows();
    if (!r) { st.textContent = "Player values are still loading. Try again in a moment."; return; }
    var name = q.replace(/\s*\([^)]*\)\s*$/, "").toLowerCase();
    var hits = r.filter(function (p) { return p.name.toLowerCase() === name; });
    if (hits.length > 1) { var exact = hits.filter(function (p) { return (p.name + " (" + p.pos + (p.team ? ", " + p.team : "") + ")") === q; }); if (exact.length) hits = exact; }
    if (hits.length !== 1) { st.textContent = hits.length ? "More than one player has that name. Check the list and add the right player." : "No player found with that name. Check the spelling."; return; }
    var p = hits[0], key = String(p.player_key);
    var owner = manual.teams.filter(function (x) { return x.players.some(function (y) { return y.key === key; }); })[0];
    if (owner) { st.textContent = p.name + " is already on " + owner.name + "."; return; }
    var ids = {}; table().forEach(function (row, i) { var k = String(row).split("|")[3]; if (k && ids[k] === undefined) ids[k] = i; });
    t.players.push({name: p.name, key: key, pos: p.pos, team: p.team, slot: "", line: p.name, id: ids[key] === undefined ? null : ids[key]});
    $("find-player").value = "";
    st.textContent = "Added " + p.name + " to " + t.name + ".";
    manualRender();
    manualSave();
  }

  /* ---------- wiring ---------- */
  /* the top of the entry flow: "Replacing: <name>" while editing; Start fresh whenever a league is kept */
  function replaced() { var raw = null; try { raw = sessionStorage.getItem("ddf:pasted"); } catch (e) { raw = null; } return !!editing && raw !== editing.pasted; }
  function showEditing() {
    var top = $("entry-top"), info = editing ? {name: editing.name || "My league"} : (DDF.leagueMeta ? DDF.leagueMeta.info() : null);
    if (!top) return;
    top.hidden = !info;
    if (!info) return;
    $("entry-top-text").textContent = editing
      ? "Replacing: " + info.name + ". Your current league stays in use until you check a new paste or enter rosters."
      : "You have a league in this browser: " + info.name + ".";
    $("entry-keep").hidden = !editing;
    if (editing && replaced()) $("entry-top-text").textContent = "Replacing: " + (editing.name || "My league") + ". Your new rosters are read: Next confirms them, or keep your current league.";
    var line = $("replacing-line");
    if (line) { line.textContent = editing ? "Replacing: " + info.name : ""; line.hidden = !editing; }
  }
  /* ---------- Sleeper (JEG-1570): the league ID loads every roster; no copy and paste ---------- */
  var SLEEPER = {h3: "Sleeper league link or ID", p: "Paste your league link or ID and we'll load every team's roster. No copying needed.",
    label: "Sleeper league link or ID", btn: "Load my league", ph: "sleeper.com/leagues/... or a number", title: "Add your Sleeper league",
    intro: "Sleeper rosters are public, so there is nothing to copy."};
  var original = null, sleeperBusy = false, sleeperLast = null;
  function provider() { var b = document.querySelector("[data-provider][aria-pressed='true']"); return b ? b.getAttribute("data-provider") : "espn"; }
  function wayEls() {
    var way = document.querySelector(".way-link");
    return way && {h3: way.querySelector("h3"), p: way.querySelector("h3 + p"), label: way.querySelector("label[for='league-ref']"),
      btn: $("get-link"), input: $("league-ref"), title: $("step1-title"), intro: $("connect-intro")};
  }
  function applyProvider() {
    var el = wayEls(); if (!el) return;
    var sl = provider() === "sleeper";
    document.body.setAttribute("data-entry-provider", provider());
    var titleText = el.title.lastChild;
    if (!original) original = {h3: el.h3.textContent, p: el.p ? el.p.textContent : "", label: el.label.textContent, btn: el.btn.textContent,
      ph: el.input.getAttribute("placeholder") || "", title: titleText ? titleText.textContent : "", intro: el.intro ? el.intro.textContent : ""};
    var src = sl ? SLEEPER : original;
    el.h3.textContent = src.h3; if (el.p) el.p.textContent = src.p; el.label.textContent = src.label; el.btn.textContent = src.btn;
    el.input.setAttribute("placeholder", src.ph); if (titleText) titleText.textContent = src.title;
    if (el.intro) el.intro.textContent = src.intro;
    $("sleeper-paste").hidden = !sl;
    $("sleeper-example").hidden = !sl;
    el.btn.classList.toggle("primary", sl);   /* one clear action on the Sleeper step */
    if (!sl) { document.body.classList.remove("show-paste"); sleeperSeq++; if (sleeperBusy) sleeperDone(el); }
    var out = $("link-result"); if (out) { out.textContent = ""; out.className = ""; }
    platformNote("");
  }
  function linkMsg(text, kind) { var out = $("link-result"); if (!out) return; out.textContent = text; out.className = kind ? "is-" + kind : ""; }

  /* ---------- the platform a pasted league link names ----------
     A link says where the league is (espn.com, yahoo.com, sleeper.com or sleeper.app), so the toggle follows it: with
     ESPN preselected, a Sleeper or Yahoo link used to build an ESPN rosters address from the wrong ID. A bare number says
     nothing about the platform and keeps the toggle as set; one as long as a Sleeper ID gets a one-tap way to Sleeper. */
  var PLATFORM_NAME = {espn: "ESPN", yahoo: "Yahoo", sleeper: "Sleeper"};
  function platformOf(text) {
    var t = String(text || "");
    if (/(?:^|[^a-z0-9-])sleeper\.(?:com|app)\b/i.test(t)) return "sleeper";
    if (/(?:^|[^a-z0-9-])espn\.com\b/i.test(t)) return "espn";
    if (/(?:^|[^a-z0-9-])yahoo\.com\b/i.test(t)) return "yahoo";
    return null;
  }
  function platformNote(html) {
    var note = $("link-platform"); if (!note) return;
    note.innerHTML = html || "";
    note.hidden = !html;
  }
  function switchTo(p) {
    var b = document.querySelector('button[data-provider="' + p + '"]');
    if (b && provider() !== p) b.click();   /* the toggle's own handlers run: help, walkthrough, this page's copy */
  }
  function followLink() {
    var el = wayEls(); if (!el) return;
    var value = el.input.value, p = platformOf(value);
    if (p && p !== provider()) {
      switchTo(p);
      platformNote("That is " + (p === "espn" ? "an " : "a ") + PLATFORM_NAME[p] + " link, so we switched to " + PLATFORM_NAME[p] + ".");
      if (p === "sleeper") sleeperGo();
      return;
    }
    if (!p && provider() !== "sleeper" && /^\s*\d{15,20}\s*$/.test(value)) {
      platformNote("That number is as long as a Sleeper league ID. " + '<button type="button" class="link-button" data-switch-provider="sleeper">My league is on Sleeper</button>');
      return;
    }
    if (!p || p === provider()) { var note = $("link-platform"); if (note && note.querySelector("[data-switch-provider]")) platformNote(""); }
  }
  var sleeperSeq = 0;
  function sleeperDone(el) { sleeperBusy = false; el.btn.disabled = false; el.btn.removeAttribute("aria-busy"); }
  function sleeperGo() {
    var el = wayEls(), id = DDF.sleeper && DDF.sleeper.parseId(el.input.value);
    if (!id) { linkMsg(el.input.value.trim() ? DDF.sleeper.MESSAGES.invalid() : "Paste your Sleeper league link or ID first.", "error"); return Promise.resolve(null); }
    if (sleeperLast === id && kept() && kept().source === "sleeper" && kept().leagueId === id) return Promise.resolve(null);
    /* a newer request (another ID, or switching away from Sleeper) wins; an older answer is dropped */
    var seq = ++sleeperSeq;
    var current = function () { return seq === sleeperSeq && provider() === "sleeper" && DDF.sleeper.parseId(el.input.value) === id; };
    sleeperBusy = true; el.btn.disabled = true; el.btn.setAttribute("aria-busy", "true");
    linkMsg("Loading your league from Sleeper...", "loading");
    return whenRows().then(function (rows) {
      return DDF.sleeper.load(id, {rows: rows, table: table()}).then(function (out) {
        if (!current()) { if (seq === sleeperSeq) { sleeperDone(el); linkMsg("", ""); } return null; }   /* the field changed meanwhile */
        sleeperDone(el);
        if (!out || !out.ok) { sleeperLast = null; linkMsg(DDF.sleeper.MESSAGES[(out && out.code) || "network"](out), "error"); return out; }
        sleeperLast = id;
        var res = out.result;
        if (out.settings && DDF.engine && DDF.engine.apply) { try { DDF.engine.apply(out.settings); } catch (e) { /* settings.html asks */ } }
        hideEditNames();
        showResult(res, "sleeper");
        /* the settings Sleeper gave (sleeper-import.js settingsOf), so settings.html can show them as read from the league */
        var srec = DDF.leaguePaste.record(res, "sleeper");
        if (out.settings) srec.importSettings = out.settings;
        save(srec);
        askBookmark(res);
        var lg = res.league || {};
        linkMsg("We found: " + (lg.leagueName || "your league") + ", " + plural(res.teams.length, "team") + ", " + plural(res.matched, "player") + ". Check the list below, then pick your team.", "ok");
        status("", "");
        return out;
      });
    }, function () {
      if (current()) { sleeperDone(el); linkMsg("Player values are still loading. Try again in a moment.", "error"); }
      return null;
    }).catch(function () { if (current()) { sleeperDone(el); linkMsg(DDF.sleeper.MESSAGES.network(), "error"); } return null; });
  }
  /* ---------- ESPN public leagues: the league ID loads every roster (espn-import.js) ----------
     connect.html's live() calls espnLookup(id, {button}) when the box holds an ESPN league ID; `button` is the rosters
     page link it would have shown. While ESPN answers, the box says "Looking up your league..."; a public league fills
     the read card (the team is picked there: ESPN's public data does not say which team is yours); a private league,
     an unknown ID, a timeout or no network falls through to that rosters link with the reason. A remembered ID on a
     return visit loads only when no league is kept in this browser. */
  var espnSeq = 0, espnLast = null;
  function espnOut(id, html, kind) {
    var out = $("link-result"); if (!out) return;
    out.className = kind ? "is-" + kind : "";
    out.innerHTML = '<span class="espn-out" data-espn="' + esc(id) + '">' + html + "</span>";
  }
  function espnShown(id) { var out = $("link-result"); return !!(out && out.querySelector('.espn-out[data-espn="' + id + '"]')); }
  function espnProgress(id, steps) {
    espnOut(id, '<strong class="espn-look-title">Looking up your league...</strong><ul class="espn-prog">' + steps.map(function (s) {
      return '<li class="' + (s.done ? "done" : "on") + '">' + esc(s.text) + "</li>";
    }).join("") + '</ul><span class="espn-look-note">Straight from ESPN to your browser. Usually a few seconds.</span>', "loading");
  }
  function espnFail(id, out, button) {
    var code = (out && out.code) || "network", msg = DDF.espn.MESSAGES[code] ? DDF.espn.MESSAGES[code](out) : DDF.espn.MESSAGES.network();
    var extra = "";
    if (code === "private") extra = '<span class="espn-why-tip">League manager? Making the league viewable to the public in ESPN\'s league settings lets everyone skip this.</span>';
    if (code === "notfound") extra = '<span class="espn-why-tip">Is your league on Yahoo? <button type="button" class="link-button" data-switch-provider="yahoo">My league is on Yahoo</button></span>';
    if (code === "timeout" || code === "network") extra = '<span class="espn-why-tip"><button type="button" class="link-button" data-espn-retry>Try again</button></span>';
    espnOut(id, '<span class="espn-why">' + esc(msg) + "</span>" + (button || "") + extra, "note");
  }
  function espnLookup(id, opts) {
    opts = opts || {};
    var el = wayEls();
    if (!DDF.espn || !el || !/^\d{1,12}$/.test(String(id || ""))) return false;
    if (espnShown(id)) return true;   /* already looking it up, loaded, or said why not */
    if (opts.restore && (kept() || (DDF.leagueMeta && DDF.leagueMeta.info()))) return false;   /* a kept league stays as it is */
    var seq = ++espnSeq, ref = DDF.espn.parseId(el.input.value) || {id: id, season: null};
    espnLast = {id: id, button: opts.button || ""};
    var inBox = new RegExp("(^|\\D)" + id + "(\\D|$)");   /* the box still holds this ID (a link, a bare number or text around it) */
    var current = function () { return seq === espnSeq && provider() === "espn" && inBox.test(el.input.value); };
    var started = Date.now();
    /* a lookup the box no longer asks for (emptied, edited, another platform) takes its progress away with it */
    var stale = function () { if (seq === espnSeq && espnShown(id)) { var o = $("link-result"); o.innerHTML = ""; o.className = ""; } };
    document.body.classList.remove("espn-loaded");
    espnProgress(id, [{text: "Asking ESPN for league " + id}]);
    /* a short pause, so typing an ID digit by digit asks ESPN once */
    setTimeout(function () {
      if (!current()) { stale(); return; }
      whenRows().then(function (rows) {
        if (!current()) { stale(); return null; }
        return DDF.espn.load(id, {rows: rows, table: table(), season: ref.season || null, onProgress: function (p) {
          if (!current()) return;
          espnProgress(id, [{text: "Found an ESPN league" + (p.name ? ": " + p.name : ""), done: true},
            {text: p.teams ? "Reading " + plural(p.teams, "roster") : "Reading every roster"}]);
        }}).then(function (out) {
          if (!current()) { stale(); return null; }
          if (!out || !out.ok) { espnFail(id, out, espnLast.button); return out; }
          var res = out.result;
          hideEditNames();
          showResult(res, "espn");
          var rec = DDF.leaguePaste.record(res, "espn");
          if (out.settings) rec.importSettings = out.settings;
          save(rec);
          askBookmark(res);
          var lg = res.league || {};
          espnOut(id, esc("We found: " + (lg.leagueName || "your league") + " on ESPN, " + plural(res.teams.length, "team") + ", " + plural(res.matched, "player")
            + ". Pick your team below.") + ' <button type="button" class="link-button" data-espn-paste>Paste the rosters page instead</button>', "ok");
          document.body.classList.add("espn-loaded");
          status("", "");
          DDF.espn.lastMs = Date.now() - started;
          var card = $("recognized"); if (card && card.scrollIntoView) card.scrollIntoView({block: "start"});
          return out;
        });
      }, function () {
        if (current()) espnOut(id, esc("Player values are still loading. Try again in a moment.") + ' <button type="button" class="link-button" data-espn-retry>Try again</button>', "note");
        return null;
      }).catch(function () { if (current()) espnFail(id, {code: "network"}, espnLast.button); });
    }, opts.delay === undefined ? 350 : opts.delay);
    return true;
  }
  /* the copy steps come back with any other league, another platform, or "Paste the rosters page instead" */
  document.addEventListener("ddf:pasted", function (e) { var r = e.detail; if (!r || r.source !== "espn") document.body.classList.remove("espn-loaded"); });
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-provider]")) setTimeout(function () { if (provider() !== "espn") document.body.classList.remove("espn-loaded"); }, 0);
    if (e.target.closest && e.target.closest("[data-espn-paste]")) { document.body.classList.add("show-paste"); $("rosters").focus(); }
  });
  document.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-espn-retry]") || !espnLast) return;
    var last = espnLast, out = $("link-result");
    if (out) out.innerHTML = "";
    espnLookup(last.id, {button: last.button, delay: 0});
  });
  function initSleeper() {
    var el = wayEls(); if (!el || !DDF.sleeper) return;
    document.addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest("button[data-provider]")) applyProvider();   /* after the toggle's own handler */
    });
    el.btn.addEventListener("click", function () { if (provider() === "sleeper") sleeperGo(); });
    el.input.addEventListener("keydown", function (e) { if (e.key === "Enter" && provider() === "sleeper") { e.preventDefault(); sleeperGo(); } });
    /* a pasted link for another platform switches the toggle first (followLink), so Sleeper loads only while Sleeper is on */
    el.input.addEventListener("paste", function () { if (provider() === "sleeper") setTimeout(function () { if (provider() === "sleeper") sleeperGo(); }, 0); });
    el.input.addEventListener("change", function () { if (provider() === "sleeper") sleeperGo(); });
    el.input.addEventListener("input", function () { sleeperLast = null; followLink(); });
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-switch-provider]");
      if (!b) return;
      var p = b.getAttribute("data-switch-provider");
      switchTo(p);
      if (p === "sleeper") sleeperGo();
    });
    $("sleeper-paste-instead").addEventListener("click", function () { document.body.classList.add("show-paste"); $("rosters").focus(); });
    applyProvider();
  }
  function init() {
    var form = $("roster-form");
    if (!form || !DDF.leaguePaste) return;
    form.addEventListener("submit", function (e) { e.preventDefault(); check(true, true); });
    var ta = $("rosters");
    ta.addEventListener("paste", function () { setTimeout(function () { check(false, true); }, 0); });
    initSleeper();
    editing = startEditing();
    if (!editing) DDF.state.remove("editprev");
    showEditing();
    document.addEventListener("ddf:pasted", showEditing);
    $("entry-keep").addEventListener("click", function () { if (editing) restoreEditing(); });
    ta.addEventListener("input", function () {
      var p = kept();
      if (p && p.source === "paste" && !editing) drop();
      hideResult();
      if (!ta.value.trim()) { status("", ""); hideEditNames(); }
    });
    $("edit-names-go").addEventListener("click", readAgain);
    var pickList = $("team-pick-list");
    if (pickList) pickList.addEventListener("change", function (e) { if (e.target && e.target.name === "team-pick") pickTeam(Number(e.target.value)); });
    /* Next from here confirms the team, as Next on setup.html does: the edit is done */
    var nextLink = $("connect-next");
    if (nextLink) nextLink.addEventListener("click", function () {
      if (!/settings\.html$/.test(nextLink.getAttribute("href") || "")) return;
      confirmTeam();
    });
    var scoringBox = $("scoring-pick");
    if (scoringBox) scoringBox.addEventListener("click", function (e) { var b = e.target.closest && e.target.closest("[data-scoring]"); if (b) pickScoring(b.getAttribute("data-scoring")); });
    /* Next (to the team page or League settings): the scoring picked on the card becomes the league's */
    var scoringNext = $("connect-next");
    if (scoringNext) scoringNext.addEventListener("click", function () { if (scoringNext.getAttribute("href")) { applyPickedScoring(); applyImported(); } });
    $("edit-team-names").addEventListener("click", editNamesFromCard);
    $("manual-names").addEventListener("input", manualNames);
    $("manual-team").addEventListener("change", manualRender);
    $("manual-add").addEventListener("click", manualAdd);
    $("find-player").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); manualAdd(); } });
    $("manual-rows").addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-remove]"), t = manual.teams[Number($("manual-team").value)];
      if (!b || !t) return;
      t.players.splice(Number(b.getAttribute("data-remove")), 1);
      manualRender();
      manualSave();
    });
    /* coming back to this page in the same tab: show what was kept */
    var p = kept();
    if (p && p.source === "manual") {
      manual.teams = p.teams.map(function (t) { return {name: t.name, players: (t.players || []).slice()}; });
      $("manual-names").value = manual.teams.map(function (t) { return t.name; }).join("\n");
      restoring = true; try { manualNames(); } finally { restoring = false; }
    } else manualRender();
    if (DDF.engine && DDF.engine.ready) DDF.engine.ready.then(fillPlayerOptions).catch(function () {});
    if (p && p.source === "paste" && ta.value.trim()) check(false);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  DDF.connectEntry = {check: check, detectDevice: detectDevice, editing: function () { return !!editing; }, sleeperGo: sleeperGo, espnLookup: espnLookup,
    platformOf: platformOf, followLink: followLink,
    teamChoice: teamChoice, pickTeam: pickTeam,
    scoringChoice: scoringChoice, pickScoring: pickScoring};
})();
