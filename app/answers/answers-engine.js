/* Answers engine (JEG-1543): the DDF numbers the answers pages show, with no source data in the browser.
 *
 * The full site runs the value engine in the page over every source's values. The answers pages never load it.
 * They read DDF outputs only, built by pipelines/answer_tables.cjs from get-values' own pipeline:
 *   data/grid.json            the pre-built settings grid
 *   data/players.json         {fields:[key,name,pos,team], rows}
 *   data/<cell>.json          one setting: {fields:[key,ddf,sd,low], rows}; a player in players.json who is not in a
 *                             cell is priced at 0 there (below the waiver line)
 * Settings outside the grid (other counts, season weeks, advanced or position-share changes) are not computed in the
 * browser: the answer is withheld with a notice (JEG-1263 rule) until the answers server serves them.
 *
 * Saved league and overrides are the full site's own stores (same origin, no second store), read only:
 *   localStorage ddf.v2.league-settings   {v:1, scoring, teams, roster, weeks?, adv?, shares?}
 *   localStorage ddf-v2-value-overrides   {v:2, basis, values:{player_key: n | {type:'adjustment', delta}}}
 * A saved basis other than the default is a source choice; it is ignored here and reported (basisIgnored).
 *
 * API: window.DDF.answers
 *   ready                      Promise<state> after the first table loads (or is withheld)
 *   settings()                 {scoring, teams, roster:{QB,RB,WR,TE,FLEX,SUPERFLEX,BENCH}}
 *   cell()                     the grid cell id for settings(), or null when off the grid
 *   offGrid()                  [] or the reasons the settings are off the grid
 *   players()                  [{key, n, pos, team, ddf, base, sd, low, ov}] for the current cell, DDF Value desc
 *   player(key)                one record or null
 *   useVisit(partial)          price another setting for this visit (never saved); returns a Promise
 *   overrideCount() / basisIgnored()
 *   on(fn)                     fn() after every change; returns an unsubscribe
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var LEAGUE_KEY = "ddf.v2.league-settings";
  var OV_KEY = "ddf-v2-value-overrides";
  var DEFAULTS = {scoring: "ppr", teams: 12, roster: {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7}};
  // The full site's default season weeks and advanced settings (curve-widget.js lineupSettings).
  var WEEKS_DEFAULT = {regularEnd: 14, playoffLo: 15, playoffHi: 17, optimize: "season"};
  var ADV_DEFAULT = {injuryHistory: "recent", projectionConfidence: 1, benchShareOverride: null};
  var OVERRIDE_MIN = 0, OVERRIDE_MAX = 100;
  var finite = function (v) { return typeof v === "number" && isFinite(v); };
  var grid = null, names = null, table = null, current = null, visit = null, listeners = [], overrides = {}, basisIgnored = false;

  function readJSON(key) { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { return null; } }
  function fetchJSON(path) {
    return fetch(path, {cache: "default"}).then(function (r) {
      if (!r.ok) throw new Error(path + " " + r.status);
      return r.json();
    });
  }

  function savedSettings() {
    var saved = readJSON(LEAGUE_KEY);
    var out = {scoring: DEFAULTS.scoring, teams: DEFAULTS.teams, roster: Object.assign({}, DEFAULTS.roster), extra: []};
    if (!saved || saved.v !== 1) return out;
    if (saved.scoring) out.scoring = saved.scoring;
    if (Number.isInteger(saved.teams)) out.teams = saved.teams;
    if (saved.roster) Object.keys(out.roster).forEach(function (k) { if (Number.isInteger(saved.roster[k])) out.roster[k] = saved.roster[k]; });
    var w = saved.weeks;
    if (w && (w.regularEnd !== WEEKS_DEFAULT.regularEnd || w.playoffLo !== WEEKS_DEFAULT.playoffLo || w.playoffHi !== WEEKS_DEFAULT.playoffHi
        || (w.optimize && w.optimize !== WEEKS_DEFAULT.optimize) || (Number.isInteger(w.content) && w.content !== w.build))) out.extra.push("season weeks");
    var a = saved.adv;
    if (a && Object.keys(ADV_DEFAULT).some(function (k) { return k in a && a[k] !== ADV_DEFAULT[k]; })) out.extra.push("advanced settings");
    if (saved.shares) out.extra.push("position shares");
    return out;
  }
  function settingsNow() { return visit || current; }

  function cellOf(s) {
    var r = s.roster, g = grid && grid.grid, why = [];
    if (!g) return {id: null, why: ["the pre-built tables did not load"]};
    var inGrid = function (list, v) { return list.indexOf(v) >= 0; };
    if (!inGrid(g.scoring, s.scoring)) why.push("scoring");
    if (!inGrid(g.teams, s.teams)) why.push("team count");
    if (!inGrid(g.sf, r.SUPERFLEX)) why.push("QB-eligible flex slots");
    if (!inGrid(g.qb, r.QB)) why.push("QB slots");
    if (!inGrid(g.wr, r.WR)) why.push("WR slots");
    if (!inGrid(g.flex, r.FLEX)) why.push("flex slots");
    if (!inGrid(g.bench, r.BENCH)) why.push("bench size");
    if (r.RB !== 2) why.push("RB slots");
    if (r.TE !== 1) why.push("TE slots");
    why = why.concat(s.extra || []);
    if (why.length) return {id: null, why: why};
    return {id: s.scoring + "-" + s.teams + "-sf" + r.SUPERFLEX + "-q" + r.QB + "w" + r.WR + "f" + r.FLEX + "-b" + r.BENCH, why: []};
  }

  function readOverrides() {
    var saved = readJSON(OV_KEY);
    overrides = {};
    basisIgnored = false;
    if (!saved || typeof saved !== "object") return;
    var basis = saved.basis;
    if (basis && typeof basis === "object" && basis.mode && basis.mode !== "default") basisIgnored = true;
    var values = saved.values && typeof saved.values === "object" ? saved.values : {};
    Object.keys(values).forEach(function (key) {
      var spec = normalizeOverride(values[key]);
      if (spec) overrides[String(key)] = spec;
    });
  }
  // value-model.js normalizeOverride / applyDdfOverride, line for line (tests/test_answers_site.py checks them against
  // ValueModel on the same cases): an absolute value is capped to 0-100 (below 0 is refused); an adjustment is capped
  // to +-100 and added to DDF Value, the sum capped to 0-100. Per player, after the pipeline: no other player moves.
  function clampValue(v) { return Math.min(OVERRIDE_MAX, Math.max(OVERRIDE_MIN, v)); }
  function absolute(raw) {
    if (raw === "") return null;
    var n = Number(raw);
    return finite(n) && n >= OVERRIDE_MIN ? {type: "absolute", value: clampValue(n)} : null;
  }
  function normalizeOverride(o) {
    if (o === null || o === undefined) return null;
    if (typeof o === "number" || typeof o === "string") return absolute(o);
    if (typeof o !== "object") return null;
    if (o.type === "adjustment") {
      if ((typeof o.delta !== "number" && typeof o.delta !== "string") || o.delta === "") return null;
      var d = Number(o.delta);
      return finite(d) ? {type: "adjustment", delta: Math.min(OVERRIDE_MAX, Math.max(-OVERRIDE_MAX, d))} : null;
    }
    if (typeof o.value !== "number" && typeof o.value !== "string") return null;
    return absolute(o.value);
  }
  function applyOverride(base, spec) {
    if (!spec) return base;
    if (spec.type === "adjustment") return clampValue((finite(base) ? base : 0) + spec.delta);
    return spec.value;
  }

  var list = [], byKey = new Map();
  function rebuild() {
    list = [];
    byKey = new Map();
    if (!table || !names) return;
    var priced = new Map();
    table.rows.forEach(function (r) { priced.set(r[0], r); });
    names.rows.forEach(function (p) {
      var row = priced.get(p[0]);
      var base = row ? row[1] : 0;
      var spec = overrides[String(p[0])] || null;
      var rec = {key: String(p[0]), n: p[1], pos: p[2], team: p[3], base: base, ddf: applyOverride(base, spec),
        sd: row ? row[2] : null, low: Boolean(row && row[3]) && !spec, ov: Boolean(spec)};
      list.push(rec);
      byKey.set(rec.key, rec);
    });
    list.sort(function (a, b) { return b.ddf - a.ddf || a.n.localeCompare(b.n); });
  }
  function changed() { listeners.slice().forEach(function (fn) { try { fn(); } catch (e) { console.error(e); } }); }

  var state = {cell: null, why: [], error: null};
  function load() {
    var c = cellOf(settingsNow());
    state.cell = c.id;
    state.why = c.why;
    state.error = null;
    if (!c.id) { table = null; rebuild(); return Promise.resolve(state); }
    return fetchJSON("data/" + c.id + ".json").then(function (t) {
      if (t.cell !== c.id) throw new Error("table " + t.cell + " is not " + c.id);
      table = t;
      rebuild();
      return state;
    }).catch(function (e) { table = null; state.error = String(e.message || e); rebuild(); return state; });
  }

  current = savedSettings();
  readOverrides();
  var ready = Promise.all([fetchJSON("data/grid.json"), fetchJSON("data/players.json")]).then(function (res) {
    grid = res[0];
    names = res[1];
    return load();
  }).catch(function (e) { state.error = String(e.message || e); return state; });

  window.addEventListener("storage", function (ev) {
    if (ev.key !== LEAGUE_KEY && ev.key !== OV_KEY) return;
    current = savedSettings();
    readOverrides();
    load().then(changed);
  });

  var SCORING_LABEL = {standard: "Standard", half_ppr: "Half PPR", ppr: "Full PPR"};
  function label(s) {
    var r = s.roster, parts = [SCORING_LABEL[s.scoring] || s.scoring, s.teams + " teams", r.QB + " QB", r.RB + " RB", r.WR + " WR", r.TE + " TE",
      r.FLEX + " flex"];
    if (r.SUPERFLEX) parts.push(r.SUPERFLEX + " QB-eligible flex");
    parts.push(r.BENCH + " bench");
    return parts.join(" · ");
  }

  DDF.answers = {
    label: label,
    ready: ready.then(function () { changed(); return state; }),
    settings: function () { var s = settingsNow(); return {scoring: s.scoring, teams: s.teams, roster: Object.assign({}, s.roster)}; },
    cell: function () { return state.cell; },
    offGrid: function () { return state.why.slice(); },
    error: function () { return state.error; },
    week: function () { return table ? table.week : null; },
    players: function () { return list.slice(); },
    player: function (key) { return byKey.get(String(key)) || null; },
    _override: {normalize: normalizeOverride, apply: applyOverride},   // tests only (the ValueModel parity check)
    overrideCount: function () { return Object.keys(overrides).length; },
    basisIgnored: function () { return basisIgnored; },
    grid: function () { return grid ? grid.grid : null; },
    useVisit: function (partial) {
      var base = settingsNow();
      var next = {scoring: base.scoring, teams: base.teams, roster: Object.assign({}, base.roster), extra: (base.extra || []).slice()};
      if (partial.scoring) next.scoring = partial.scoring;
      if (partial.teams) next.teams = Number(partial.teams);
      if (partial.roster) Object.keys(partial.roster).forEach(function (k) { next.roster[k] = Number(partial.roster[k]); });
      visit = next;
      return load().then(function (s) { changed(); return s; });
    },
    on: function (fn) { listeners.push(fn); return function () { listeners = listeners.filter(function (f) { return f !== fn; }); }; }
  };
})();
