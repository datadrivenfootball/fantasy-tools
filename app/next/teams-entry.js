/* teams.html, "Edit teams" (JEG-1740): change the league's rosters by hand after setup, and paste again when they are old.
 *
 * Jeremy, 2026-11-28: "a screen for editing teams after everything is loaded. The screen should recommend redoing the
 * paste after time has passed, with a link to essentially start the paste over (but preserve the league settings and
 * your team.). But you still should be able to modify teams easily."
 *
 * The league is the one every page reads (ddf-league.js read order), edited where it lives:
 *   link    a chat link league (DDF.link.current().teams): DDF.link.update({teams}); a player is a table id or a name
 *   pasted  sessionStorage ddf:pasted (connect/setup): rec.teams[i].name / players / unmatched; the live store copy is
 *           updated with DDF.setupEntry.bridge, which writes only a league this tab wrote (it never replaces another)
 *   saved   localStorage ddf.v2.workspaces (a returning visitor): the active workspace's teams[i].name / entries
 * Your team (`me`, Viewing as) is a team index, so a rename keeps it. Hand edits never change the roster date
 * (enteredAt): the freshness card keeps recommending a new paste as the rosters age. Waivers' roster moves (ddf:moves)
 * stay their own layer. Undo is kept in memory for this visit (no storage key).
 *
 * "Paste rosters again" opens connect.html?edit=1&again=1: the edit flow (JEG-1568) with the league's settings, name
 * and your team kept (connect-entry.js `again`).
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var WS_KEY = "ddf.v2.workspaces";
  var POS_ORDER = {QB: 0, RB: 1, WR: 2, TE: 3, K: 4, DEF: 5, DST: 5};
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); };
  var plural = function (n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); };
  var clone = function (x) { return JSON.parse(JSON.stringify(x)); };
  var cleanName = function (s) { return Array.from(String(s || "").replace(/\s+/g, " ").trim()).slice(0, 40).join("").trim(); };

  /* ---------- the league, where it lives ---------- */
  function readStore() {
    try { var d = JSON.parse(localStorage.getItem(WS_KEY) || "null"); return d && d.v === 1 && Array.isArray(d.workspaces) ? d : null; }
    catch (e) { return null; }
  }
  function activeWs(store) { return store ? (store.workspaces.filter(function (w) { return w && w.id === store.activeId; })[0] || store.workspaces[0]) : null; }
  function linkLeague() { try { var s = DDF.link && DDF.link.current && DDF.link.current(); return s && Array.isArray(s.teams) && s.teams.length ? s : null; } catch (e) { return null; } }
  function linkPlayer(p) {
    var info = DDF.link && DDF.link.player ? DDF.link.player(p) : {};
    return {name: info.name || (typeof p === "string" ? p : "Player " + p), key: info.key || null, pos: info.pos || "", team: info.team || "", raw: p};
  }

  /* -> {kind, me, source, teams:[{name, players:[{name, key, pos, team, raw, kdef?}], unmatched:[raw], countOnly}]} or null */
  function load() {
    var st = linkLeague();
    if (st) {
      return {kind: "link", source: "link", me: Number.isInteger(st.me) ? st.me : null, teams: st.teams.map(function (t, i) {
        return {name: String((t && t.name) || "Team " + (i + 1)), players: (Array.isArray(t && t.players) ? t.players : []).map(linkPlayer), unmatched: [], countOnly: null};
      })};
    }
    var rec = DDF.state && DDF.state.get("pasted", null);
    if (rec && Array.isArray(rec.teams) && rec.teams.length) {
      return {kind: "pasted", source: rec.source || "paste", me: Number.isInteger(rec.me) ? rec.me : null, teams: rec.teams.map(function (t, i) {
        var list = Array.isArray(t && t.players) ? t.players : [];
        var un = Array.isArray(t && t.unmatched) ? t.unmatched : [];
        var players = list.map(function (e) { return {name: String(e.name || e.line || ""), key: e.key ? String(e.key) : null, pos: String(e.pos || ""), team: String(e.team || ""), raw: e}; })
          /* K and DEF lines the paste read (reason kdef, with a key) are rostered players: they edit like the rest */
          .concat(un.filter(function (u) { return u && u.reason === "kdef" && u.key; }).map(function (u) {
            return {name: String(u.line || ""), key: String(u.key), pos: String(u.pos || ""), team: String(u.team || ""), raw: u, kdef: true};
          }));
        return {name: String((t && t.name) || "Team " + (i + 1)), players: players,
          unmatched: un.filter(function (u) { return u && !(u.reason === "kdef" && u.key); }),
          countOnly: Array.isArray(t && t.players) ? null : (Number(t && t.players) || 0)};
      })};
    }
    var ws = activeWs(readStore());
    if (ws && Array.isArray(ws.teams) && ws.teams.length) {
      var me = null;
      var teams = ws.teams.map(function (t, i) {
        if (t && ws.myTeamId !== null && ws.myTeamId !== undefined && String(t.id) === String(ws.myTeamId)) me = i;
        return {name: String((t && t.name) || "Team " + (i + 1)), unmatched: [], countOnly: null,
          players: (Array.isArray(t && t.entries) ? t.entries : []).map(function (e) { return {name: String(e.name || ""), key: e.key ? String(e.key) : null, pos: String(e.pos || ""), team: String(e.team || ""), raw: e}; })};
      });
      return {kind: "saved", source: "saved", me: me, teams: teams};
    }
    return null;
  }

  /* model -> store. Returns true when saved. */
  function save(model) {
    try {
      if (model.kind === "link") {
        var st = linkLeague(); if (!st) return false;
        DDF.link.update({teams: st.teams.map(function (t, i) {
          var m = model.teams[i];
          return Object.assign({}, t, {name: m.name, players: m.players.map(function (p) { return p.raw; })});
        })});
        return true;
      }
      if (model.kind === "pasted") {
        var rec = DDF.state.get("pasted", null); if (!rec || !Array.isArray(rec.teams)) return false;
        rec.teams = rec.teams.map(function (t, i) {
          var m = model.teams[i], o = Object.assign({}, t, {name: m.name});
          if (m.countOnly !== null && !m.touched) return o;
          o.players = m.players.filter(function (p) { return !p.kdef; }).map(function (p) { return p.raw; });
          o.unmatched = m.players.filter(function (p) { return p.kdef; }).map(function (p) { return p.raw; }).concat(m.unmatched);
          return o;
        });
        DDF.state.set("pasted", rec);
        /* the live pages' copy: only a league this tab wrote is updated; another saved league is never replaced here */
        if (Number.isInteger(rec.me) && DDF.setupEntry && DDF.setupEntry.bridge && DDF.state.get("bridgedWs", null)) DDF.setupEntry.bridge(rec);
        document.dispatchEvent(new CustomEvent("ddf:pasted", {detail: rec}));
        return true;
      }
      if (model.kind === "saved") {
        var store = readStore(), ws = activeWs(store); if (!ws) return false;
        var now = Date.now();
        ws.teams = ws.teams.map(function (t, i) {
          var m = model.teams[i];
          var changed = m.name !== t.name || JSON.stringify(m.players.map(function (p) { return p.raw; })) !== JSON.stringify(t.entries || []);
          if (!changed) return t;
          return Object.assign({}, t, {name: m.name, entries: m.players.map(function (p) { return p.raw; }), updatedAt: now,
            provenance: Object.assign({}, t.provenance || {}, {editedAt: now})});
        });
        ws.updatedAt = now;
        localStorage.setItem(WS_KEY, JSON.stringify(store));
        return true;
      }
    } catch (e) { return false; }
    return false;
  }

  /* ---------- players to add (the engine's rows, as connect.html's manual entry finds them) ---------- */
  var rowsCache = null;
  function rows() {
    if (rowsCache) return rowsCache;
    var C = DDF.engine && DDF.engine.controls && DDF.engine.controls();
    if (!C || !C.getAllRows) return null;
    rowsCache = C.getAllRows().filter(function (r) { return r && r.name && r.player_key !== undefined && r.player_key !== null; })
      .map(function (r) { return {key: String(r.player_key), name: r.name, pos: r.pos || "", team: r.team || ""}; });
    return rowsCache;
  }
  var label = function (p) { return p.name + " (" + p.pos + (p.team ? ", " + p.team : "") + ")"; };
  function tableIds() {
    var ids = {}, t = [];
    try { var st = linkLeague(); t = (DDF.link && DDF.link.table && DDF.link.table((st && st.table) || 1)) || []; } catch (e) { t = []; }
    t.forEach(function (row, i) { var k = String(row).split("|")[3]; if (k && ids[k] === undefined) ids[k] = i; });
    return ids;
  }
  /* a stored entry for a new player, in the shape of the league it joins */
  function newEntry(p) {
    var id = tableIds()[p.key];
    if (model.kind === "link") return {name: p.name, key: p.key, pos: p.pos, team: p.team, raw: id === undefined ? p.name : id};
    if (model.kind === "saved") return {name: p.name, key: p.key, pos: p.pos, team: p.team, raw: {key: p.key, name: p.name, pos: p.pos, team: p.team}};
    return {name: p.name, key: p.key, pos: p.pos, team: p.team,
      raw: {name: p.name, key: p.key, pos: p.pos, team: p.team, slot: "", line: p.name, id: id === undefined ? null : id}};
  }

  /* ---------- page state ---------- */
  var model = null, current = 0, undo = [], pendingLine = null;

  /* roster: the change touches players (a rename alone keeps a count-only team as it was) */
  function change(fn, message, roster) {
    var before = clone(model.teams);
    fn();
    if (roster) model.teams[current].touched = true;
    if (!save(model)) { model.teams = before; status("That did not save. Try again.", "warn"); render(); return false; }
    undo.push({teams: before, at: current});
    if (undo.length > 50) undo.shift();
    if (DDF.leagueMeta && DDF.leagueMeta.refresh) DDF.leagueMeta.refresh();
    if (DDF.refreshNav) DDF.refreshNav();
    render();
    status(message, "ok");
    return true;
  }
  function status(text, tone, html) {
    var el = $("tm-status");
    if (html) el.innerHTML = html; else el.textContent = text || "";
    el.setAttribute("data-tone", tone || "");
  }

  function freshness() {
    var M = DDF.leagueMeta, info = M && M.info ? M.info() : null;
    var days = info ? info.days : null, band = info && info.band ? info.band : (days === null || days === undefined ? "unknown" : "fresh");
    var when = days === null || days === undefined ? null : M.ageWords(days);
    var box = $("tm-fresh"), again = $("tm-again");
    var imported = model.source === "sleeper" || model.source === "espn";
    box.setAttribute("data-band", band);
    again.textContent = imported ? "Load rosters again" : "Paste rosters again";
    var redo = imported ? "Loading your league again" : "Pasting your league again";
    if (band === "fresh") {
      $("tm-fresh-title").textContent = "Rosters entered " + when;
      $("tm-fresh-text").textContent = "Fix small changes here. When rosters change a lot, " + redo.charAt(0).toLowerCase() + redo.slice(1) + " catches every move at once.";
    } else if (band === "unknown") {
      $("tm-fresh-title").textContent = "We do not know when these rosters were entered";
      $("tm-fresh-text").textContent = "If it has been more than a day or two, " + redo.charAt(0).toLowerCase() + redo.slice(1) + " is the quickest way to catch every waiver pickup and trade.";
    } else {
      $("tm-fresh-title").textContent = band === "note" ? "Rosters entered " + when : "Rosters entered " + when + ". Time to " + (imported ? "load" : "paste") + " again?";
      $("tm-fresh-text").textContent = "Waivers, trades and injuries change rosters every week. " + redo + " catches every move at once, which is quicker than fixing teams one by one.";
    }
    again.classList.toggle("primary", band !== "fresh");
  }

  function render() {
    var teams = model.teams;
    if (!teams[current]) current = 0;
    $("tm-teams").innerHTML = teams.map(function (t, i) {
      var n = t.countOnly !== null && !t.touched ? t.countOnly : t.players.length;
      return '<li><button type="button" data-team="' + i + '" aria-pressed="' + (i === current) + '">' + esc(t.name)
        + (i === model.me ? '<span class="tm-mine">Your team</span>' : "") + "<small>" + n + "</small></button></li>";
    }).join("");
    var t = teams[current];
    $("tm-editor-title").innerHTML = esc(t.name) + (current === model.me ? ' <span class="tm-mine">Your team</span>' : "");
    var count = t.countOnly !== null && !t.touched ? t.countOnly : t.players.length;
    $("tm-editor-sub").textContent = t.countOnly !== null && !t.touched
      ? plural(count, "player") + " counted in your paste, but their names were not kept. Add players to list them here."
      : plural(count, "player") + (t.unmatched.length ? " · " + plural(t.unmatched.length, "line") + " to check" : "");
    var nameIn = $("tm-name");
    if (document.activeElement !== nameIn) nameIn.value = t.name;
    $("tm-roster-cap").textContent = "Players on " + t.name;
    var list = t.players.map(function (p, i) { return {p: p, i: i}; }).sort(function (a, b) {
      var pa = POS_ORDER[a.p.pos.toUpperCase()], pb = POS_ORDER[b.p.pos.toUpperCase()];
      pa = pa === undefined ? 9 : pa; pb = pb === undefined ? 9 : pb;
      return pa - pb || a.p.name.localeCompare(b.p.name);
    });
    $("tm-rows").innerHTML = list.length ? list.map(function (x) {
      return "<tr><td>" + esc(x.p.name) + '</td><td class="pos">' + esc(x.p.pos === "DST" ? "DEF" : x.p.pos) + "</td><td>" + esc(x.p.team) + '</td><td><button type="button" class="link-button" data-remove="' + x.i + '">Remove<span class="sr-only"> ' + esc(x.p.name) + "</span></button></td></tr>";
    }).join("") : '<tr><td colspan="4" class="muted">No players on this team yet. Find a player above and add them.</td></tr>';
    var un = $("tm-unmatched");
    un.hidden = !t.unmatched.length;
    $("tm-unmatched-list").innerHTML = t.unmatched.map(function (u, i) {
      return "<li><span>" + esc(u.line || u.name || "") + '</span><button type="button" class="link-button" data-find="' + i + '">Find this player<span class="sr-only"> ' + esc(u.line || "") + '</span></button><button type="button" class="link-button" data-dismiss="' + i + '">Remove line<span class="sr-only"> ' + esc(u.line || "") + "</span></button></li>";
    }).join("");
    var moves = DDF.state ? DDF.state.get("moves", []) : [];
    var mv = $("tm-moves"), nMoves = Array.isArray(moves) ? moves.length : 0;
    mv.hidden = !(current === model.me && nMoves);
    if (!mv.hidden) mv.textContent = "Your " + plural(nMoves, "roster move") + " from Waivers " + (nMoves === 1 ? "is" : "are") + " added on top of this roster on the other pages.";
    $("tm-undo").disabled = !undo.length;
  }

  /* ---------- actions ---------- */
  function pick(i) { current = i; pendingLine = null; status(""); render(); $("tm-editor-title").focus({preventScroll: false}); }
  function rename() {
    var t = model.teams[current], v = cleanName($("tm-name").value);
    if (!v) { $("tm-name").value = t.name; status("A team needs a name.", "warn"); return; }
    if (v === t.name) return;
    var taken = model.teams.some(function (x, i) { return i !== current && x.name.toLowerCase() === v.toLowerCase(); });
    if (taken) { status("Another team already has that name.", "warn"); return; }
    var old = t.name;
    change(function () { model.teams[current].name = v; }, "Renamed " + old + " to " + v + ".");
  }
  function owner(key) {
    for (var i = 0; i < model.teams.length; i++) if (model.teams[i].players.some(function (p) { return p.key === key; })) return i;
    return -1;
  }
  function find(q) {
    var r = rows();
    if (!r) return {error: "Player values are still loading. Try again in a moment."};
    var name = q.replace(/\s*\([^)]*\)\s*$/, "").trim().toLowerCase();
    if (!name) return {error: "Type a player's name first."};
    var hits = r.filter(function (p) { return p.name.toLowerCase() === name; });
    if (hits.length > 1) { var exact = hits.filter(function (p) { return label(p) === q.trim(); }); if (exact.length) hits = exact; }
    if (!hits.length) return {error: "No player found with that name. Check the spelling, or pick from the list as you type."};
    if (hits.length > 1) return {error: "More than one player has that name. Pick the right one from the list as you type."};
    return {player: hits[0]};
  }
  function clearFind() { $("tm-find").value = ""; pendingLine = null; }
  function add() {
    var q = $("tm-find").value, res = find(q), t = model.teams[current];
    if (res.error) { status(res.error, "warn"); return; }
    var p = res.player, at = owner(p.key);
    if (at === current) { status(p.name + " is already on " + t.name + ".", "warn"); return; }
    if (at >= 0) {
      status("", "warn", esc(p.name) + " is on " + esc(model.teams[at].name) + '. <button type="button" class="primary" id="tm-move" data-key="' + esc(p.key) + '" data-from="' + at + '">Move to ' + esc(t.name) + "</button>");
      return;
    }
    var line = pendingLine;
    change(function () {
      var team = model.teams[current];
      team.players.push(newEntry(p));
      if (line !== null && team.unmatched[line]) team.unmatched.splice(line, 1);
    }, "Added " + p.name + " to " + t.name + ".", true);
    clearFind();
    $("tm-find").focus();
  }
  function move(key, from) {
    var src = model.teams[from], i = src ? src.players.map(function (p) { return p.key; }).indexOf(key) : -1;
    if (i < 0) return;
    var p = src.players[i], dest = model.teams[current], line = pendingLine;
    change(function () {
      var moved = model.teams[from].players.splice(i, 1)[0];
      model.teams[from].touched = true;
      model.teams[current].players.push(moved);
      if (line !== null && model.teams[current].unmatched[line]) model.teams[current].unmatched.splice(line, 1);
    }, "Moved " + p.name + " from " + src.name + " to " + dest.name + ".", true);
    clearFind();
    $("tm-find").focus();
  }
  function remove(i) {
    var t = model.teams[current], p = t.players[i];
    if (!p) return;
    change(function () { model.teams[current].players.splice(i, 1); }, "Removed " + p.name + " from " + t.name + ".", true);
    var next = document.querySelector("#tm-rows [data-remove]");
    (next || $("tm-find")).focus();
  }
  function findLine(i) {
    var u = model.teams[current].unmatched[i];
    if (!u) return;
    pendingLine = i;
    var input = $("tm-find");
    input.value = String(u.line || u.name || "").replace(/\s+(QB|RB|WR|TE|K|DEF|DST)\b.*$/i, "").trim();
    input.focus();
    input.select();
    status("Pick the right player from the list, then Add player.", "");
  }
  function dismissLine(i) {
    var u = model.teams[current].unmatched[i];
    if (!u) return;
    change(function () { model.teams[current].unmatched.splice(i, 1); if (pendingLine === i) pendingLine = null; }, "Removed the line " + (u.line || "") + ".", true);
  }
  function undoLast() {
    var last = undo.pop();
    if (!last) return;
    var now = model.teams;
    model.teams = last.teams;
    if (!save(model)) { model.teams = now; undo.push(last); status("That did not save. Try again.", "warn"); return; }
    current = last.at;
    if (DDF.leagueMeta && DDF.leagueMeta.refresh) DDF.leagueMeta.refresh();
    render();
    status("Undone.", "ok");
  }

  function fillOptions() {
    var r = rows();
    if (r) $("tm-options").innerHTML = r.map(function (p) { return '<option value="' + esc(label(p)) + '"></option>'; }).join("");
  }

  function init() {
    model = load();
    if (!model) { $("tm-none").hidden = false; return; }
    $("tm-main").hidden = false;
    var va = DDF.viewAs && DDF.viewAs.read ? DDF.viewAs.read() : null;
    if (va && va.own !== null && va.own !== undefined && model.teams[va.own]) model.me = va.own;
    var want = /[?&]team=(\d+)/.exec(location.search);
    current = want && model.teams[Number(want[1])] ? Number(want[1]) : (model.me !== null && model.teams[model.me] ? model.me : 0);
    freshness();
    render();
    $("tm-teams").addEventListener("click", function (e) { var b = e.target.closest && e.target.closest("[data-team]"); if (b) pick(Number(b.getAttribute("data-team"))); });
    $("tm-rename").addEventListener("click", rename);
    $("tm-name").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); rename(); } });
    $("tm-name").addEventListener("change", rename);
    $("tm-add").addEventListener("click", add);
    $("tm-find").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); add(); } });
    $("tm-status").addEventListener("click", function (e) { var b = e.target.closest && e.target.closest("#tm-move"); if (b) move(b.getAttribute("data-key"), Number(b.getAttribute("data-from"))); });
    $("tm-rows").addEventListener("click", function (e) { var b = e.target.closest && e.target.closest("[data-remove]"); if (b) remove(Number(b.getAttribute("data-remove"))); });
    $("tm-unmatched-list").addEventListener("click", function (e) {
      var f = e.target.closest && e.target.closest("[data-find]"), d = e.target.closest && e.target.closest("[data-dismiss]");
      if (f) findLine(Number(f.getAttribute("data-find")));
      if (d) dismissLine(Number(d.getAttribute("data-dismiss")));
    });
    $("tm-undo").addEventListener("click", undoLast);
    if (DDF.engine && DDF.engine.ready) DDF.engine.ready.then(fillOptions, function () { /* the add box says values are loading */ });
    else fillOptions();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
  DDF.teamsEntry = {load: load, save: save};
})();
