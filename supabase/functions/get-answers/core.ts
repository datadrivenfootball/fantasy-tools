// JEG-1543 phase 2: the pure core of the get-answers edge function (no Deno APIs, so node tests run it).
//
// get-answers returns Trade & Waiver Recommendations computed exactly as the full site's find.html computes them, but
// with no source data in the reply (Jeremy, 2026-11-08: the answers version shows no source names or per-source
// numbers). No value math lives here:
//   - the values are get-values' own pipeline (league.ts mapLeague, pipeline.ts planWeek / buildPipelineInput, then
//     ValueModel.runValuePipeline from the published value-model.js);
//   - the engine rows are built the way the page engine builds them (curve-widget.js buildRow / setCompositeFields in
//     the default "indexed" view), behind a read-only stand-in for TradeValueCurveControls (makeControls);
//   - the search, fit, waiver alternative, Why, partner order and opportunity tier are the site's own page modules
//     (v2/finder.js, v2/waivers.js, find-engine.js, ddf-league.js, ddf-opportunity.js, ddf-why.js, ...), loaded from
//     the published site and run in a fresh window-like sandbox per request (runPageModules);
//   - this file replays find-page.js's run() / visible() orchestration (partners, waiver pool, sort order), which is
//     page code bound to the DOM and cannot be loaded.
// The reply carries only DDF numbers, words and player keys (REPLY_SPEC), checked by validateReply before it is sent.
// Decisions (Jeremy, 2026-11-08): D3 the other team's side is judged as on the full site (Analyst charts, here on the
// server) and the reply shows a word and the percent; D4 partner ties are ordered on the server.

import { type League, type LineupDefaults, mapLeague } from "../get-values/league.ts";
import { type Bundle, buildPipelineInput, planWeek } from "../get-values/pipeline.ts";
import { canReadStrictly, readValueContext } from "../get-values/value-context.ts";

// deno-lint-ignore no-explicit-any
type Any = any;

// ---------------------------------------------------------------------------------------------------------------------
// The page modules, in find.html's load order (published paths under the site origin).
// ---------------------------------------------------------------------------------------------------------------------
export const PAGE_SCRIPTS = [
  "v2/ddf-value-link.js", "v2/trade.js", "v2/finder.js", "ddf-opportunity.js", "v2/team-summary.js", "v2/nfl-byes.js",
  "v2/player-status.js", "v2/waivers.js", "ddf-engine.js", "ddf-league.js", "find-engine.js", "ddf-why.js",
] as const;

// The globals a page script may read as bare names; each request's sandbox supplies its own.
const SANDBOX_PARAMS = ["window", "self", "document", "localStorage", "sessionStorage", "location", "history", "navigator",
  "module", "exports", "define"];

export type CompiledScript = { path: string; run: (win: Any) => void };

/** Compile each page script once (new Function, not eval: every run gets its own window object). */
export function compileScripts(sources: Record<string, string>): CompiledScript[] {
  return PAGE_SCRIPTS.map((path) => {
    const src = sources[path];
    if (typeof src !== "string" || !src.length) throw new Error(`page script missing: ${path}`);
    const fn = new Function(...SANDBOX_PARAMS, src);
    return {
      path,
      run: (win: Any) => fn.call(win, win, win, win.document, win.localStorage, win.sessionStorage, win.location,
        win.history, win.navigator, undefined, undefined, undefined),
    };
  });
}

function memoryStorage(seed: Record<string, string> = {}) {
  const data = new Map<string, string>(Object.entries(seed));
  return {
    getItem: (k: string) => (data.has(String(k)) ? data.get(String(k))! : null),
    setItem: (k: string, v: unknown) => { data.set(String(k), String(v)); },
    removeItem: (k: string) => { data.delete(String(k)); },
    clear: () => data.clear(),
    key: (i: number) => [...data.keys()][i] ?? null,
    get length() { return data.size; },
  };
}

const noop = () => {};
function stubElement(): Any {
  return { style: {}, dataset: {}, classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    setAttribute: noop, removeAttribute: noop, getAttribute: () => null, appendChild: noop, append: noop,
    addEventListener: noop, removeEventListener: noop, querySelector: () => null, querySelectorAll: () => [] };
}

/** A fresh window-like object: storage in memory, no DOM. readyState "loading" keeps each page's DOM start() unrun. */
export function makeWindow(controls: Any, session: Record<string, string>): Any {
  // Own properties shadow the real globals (some of which, like navigator, are getter-only on the prototype).
  // deno-lint-ignore no-explicit-any
  const win: Any = Object.create(globalThis as any);
  const put = (k: string, v: unknown) => Object.defineProperty(win, k, { value: v, writable: true, configurable: true, enumerable: true });
  put("document", {
    readyState: "loading", head: null, body: null, documentElement: stubElement(),
    addEventListener: noop, removeEventListener: noop, dispatchEvent: () => true,
    querySelector: () => null, querySelectorAll: () => [], getElementById: () => null, createElement: stubElement,
  });
  put("localStorage", memoryStorage());
  put("sessionStorage", memoryStorage(session));
  put("location", { hash: "", search: "", href: "https://answers.invalid/find.html", pathname: "/find.html", origin: "https://answers.invalid" });
  put("history", { replaceState: noop, pushState: noop });
  put("navigator", { userAgent: "get-answers" });
  put("addEventListener", noop);
  put("removeEventListener", noop);
  put("dispatchEvent", () => true);
  put("matchMedia", () => ({ matches: false, addEventListener: noop, removeEventListener: noop, addListener: noop }));
  put("innerWidth", 1280);
  put("confirm", () => false);
  put("TradeValueCurveControls", controls);
  for (const k of ["DDF", "TradeValueFinder", "TradeValueWaivers", "TradeValueTrade", "TradeValueTeamSummary", "TradeValueByes",
    "TradeValueStatus", "DDFOpportunity", "DDFWhy", "DDFValueLink"]) put(k, undefined);
  // site.js's DDF.state (the session store the workspace pages share), the only part of site.js these modules read.
  const PREFIX = "ddf:";
  put("DDF", {
    state: {
      get: (key: string, fallback: unknown) => {
        try { const v = win.sessionStorage.getItem(PREFIX + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
      },
      set: (key: string, value: unknown) => { win.sessionStorage.setItem(PREFIX + key, JSON.stringify(value)); return true; },
      remove: (key: string) => { win.sessionStorage.removeItem(PREFIX + key); },
    },
  });
  return win;
}

/** Run the page modules in a fresh window. A script that throws after publishing its API (no DOM) is not a failure. */
export function runPageModules(scripts: CompiledScript[], win: Any): string[] {
  const notes: string[] = [];
  for (const s of scripts) {
    try { s.run(win); } catch (e) { notes.push(`${s.path}: ${String((e as Error)?.message ?? e)}`); }
  }
  const missing = [["TradeValueFinder", "findTrades"], ["TradeValueWaivers", "evaluateAll"], ["DDFOpportunity", "computeTeam"],
    ["DDFWhy", "explain"]].filter(([g, fn]) => !win[g] || typeof win[g][fn] !== "function").map(([g]) => g);
  if (!win.DDF?.find?.searchPartner) missing.push("DDF.find");
  if (!win.DDF?.league?.partnerRank) missing.push("DDF.league");
  if (!win.DDF?.engine?.players) missing.push("DDF.engine");
  if (missing.length) throw new Error(`page modules did not load: ${missing.join(", ")} (${notes.join("; ")})`);
  return notes;
}

// ---------------------------------------------------------------------------------------------------------------------
// Engine rows and the TradeValueCurveControls stand-in (curve-widget.js, default "indexed" view).
// ---------------------------------------------------------------------------------------------------------------------
const POSITION_ORDER = ["QB", "RB", "WR", "TE"];
const SOURCE_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs", "espn", "cbsros", "razzball",
  "fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"];
const PURE_VORP_KEYS = ["espn_vorp", "cbsros_vorp", "razzball_vorp"];
const VISIBLE_KEYS = [...SOURCE_KEYS, ...PURE_VORP_KEYS];
const PIPELINE_SOURCE_KEYS = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"];
const ADJUSTED_INDEXED_KEYS = ["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted"];
const ALIASES: Record<string, string> = Object.fromEntries(ADJUSTED_INDEXED_KEYS.map((k) => [k, k.replace(/_adjusted$/, "")]));
const AS_PUBLISHED = new Set(["usatoday", "fantasycalc", "fantasypros", "cbs"]);
const COMPOSITE_VERSIONS: Record<string, string> = { ddf_value: "blended", ddf_value_charts: "charts", ddf_value_projections: "projections" };
const OVERRIDE_VERSIONS = ["ddf_value"];
const DEFAULT_BENCH_SHARE = 0.15;
const DEFAULT_ROSTER: Record<string, number> = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0, BENCH: 7, K: 1, DST: 1 };
const NONE_REASON = "No source prices this player";
const EMPTY_REASON = "No source available this week";
const ONE_SOURCE_NOTE = "Only one source prices this player";

// curve-widget seriesSource / seriesField with viewMode "indexed" (VP-11).
const seriesSource = (key: string) => PIPELINE_SOURCE_KEYS.includes(key) ? key
  : ALIASES[key] || (PURE_VORP_KEYS.includes(key) ? key.slice(0, -5) : null);
const seriesField = (key: string) => PURE_VORP_KEYS.includes(key) ? "vorp" : ADJUSTED_INDEXED_KEYS.includes(key) ? "adjusted"
  : AS_PUBLISHED.has(key) ? "indexed" : "adjusted";

/** product-data.js buildPlayers + curve-widget buildCanonicalMap over the players-data island. */
export function canonicalPlayers(island: Any[]): Map<number, Any> {
  const map = new Map<number, Any>();
  for (const p of island || []) {
    const key = Number(p.player_key);
    const name = String(p.full_name || p.name || "").trim();
    const pos = String(p.pos || "");
    if (!Number.isInteger(key) || !name || !POSITION_ORDER.includes(pos)) continue;
    map.set(key, {
      player_key: key, name, team: String(p.team || "—"), pos,
      espn_ppg: p.espn_ppg || null, rz_ppg: p.rz_ppg || null, cbsros_ppg: p.cbsros_ppg || null,
      projectionSource: p.espn_ppg ? "ESPN" : null, espnProjectsZero: p.espn_projects_zero === true,
      roster_status: p.roster_status || null, roster_status_label: p.roster_status_label || null,
      roster_status_inferred: p.roster_status_inferred === true, injury_status: p.injury_status || null,
      depth_chart_position: p.depth_chart_position || null,
      depth_chart_order: Number.isFinite(Number(p.depth_chart_order)) && p.depth_chart_order !== null ? Number(p.depth_chart_order) : null,
      sleeper_id: p.sleeper_id || null, universe_only: p.universe_only === true, unpriced_reason: p.unpriced_reason || null,
    });
  }
  return map;
}

/** The roster shape the page engine holds: the mapped league plus K / DST (0-3, default 1; they never change values). */
export function rosterShapeOf(league: League, mapped: Any): Record<string, number> {
  const s = mapped.setting;
  const kd = (k: string) => {
    const n = Math.round(Number(league?.roster?.[k]));
    return Number.isFinite(n) ? Math.max(0, Math.min(3, n)) : DEFAULT_ROSTER[k];
  };
  return { QB: s.slots.QB, RB: s.slots.RB, WR: s.slots.WR, TE: s.slots.TE, FLEX: s.flex, SUPERFLEX: s.superflex,
    BENCH: s.bench_per_team, K: kd("K"), DST: kd("DST") };
}

/** Engine rows (getAllRows) as curve-widget builds them: every pipeline row with a canonical QB/RB/WR/TE player. */
export function buildRows(ValueModel: Any, pipeline: Any, canonical: Map<number, Any>, overrides: Record<string, unknown>): Any[] {
  const rows = pipeline.rows || {};
  const sourceMaps = new Map<string, Map<number, number>>();
  for (const key of VISIBLE_KEYS) {
    const source = seriesSource(key), field = seriesField(key), out = new Map<number, number>();
    if (source && pipeline.sources?.[source]) {
      for (const [pk, row] of Object.entries(rows)) {
        const v = (row as Any)[field]?.[source];
        if (typeof v === "number" && Number.isFinite(v)) out.set(Number(pk), v);
      }
    }
    sourceMaps.set(key, out);
  }
  const ov = new Map<number, Any>();
  for (const [k, v] of Object.entries(overrides || {})) {
    const spec = ValueModel.normalizeOverride(v);
    if (Number.isInteger(Number(k)) && spec) ov.set(Number(k), spec);
  }
  const included = (pipeline.sources && Object.keys(pipeline.sources).length) || 0;
  return Object.keys(rows).map(Number).map((pk) => canonical.get(pk)).filter(Boolean).map((player: Any) => {
    const now = rows[player.player_key];
    const values: Record<string, number | null> = {};
    for (const key of VISIBLE_KEYS) {
      const v = sourceMaps.get(key)!.get(player.player_key);
      // A pipeline row always exists here, so VP-6.2's implied 0 (a player with no pipeline row) never applies.
      values[key] = v === undefined ? null : v;
    }
    const estimated: Record<string, string> = {};
    Object.entries(now.estimated || {}).forEach(([source, reason]) => {
      estimated[source] = reason as string;
      ADJUSTED_INDEXED_KEYS.filter((k) => ALIASES[k] === source).forEach((k) => { estimated[k] = reason as string; });
    });
    const row: Any = { ...player, values, missingReasons: {}, estimated, meanPpg: now.meanPpg };
    // setCompositeFields (VP-6.3): the three DDF versions, then the reader's override on the blended one.
    row.ddfByVersion = Object.fromEntries(Object.entries(COMPOSITE_VERSIONS).map(([version, name]) => {
      const cur = now.ddfByVersion?.[name];
      const value = cur && Number.isFinite(cur.value) ? cur.value : null;
      const count = cur ? cur.count : 0;
      const entry: Any = { value, count, sources: cur ? [...cur.sources] : [],
        reason: value !== null ? null : (!included ? EMPTY_REASON : NONE_REASON),
        lowConfidence: count === 1, confidenceNote: count === 1 ? ONE_SOURCE_NOTE : null,
        prior: null, priorCount: 0, priorLowConfidence: false };
      row.values[version] = entry.value;
      return [name, entry];
    }));
    const override = ov.has(player.player_key) ? ov.get(player.player_key) : null;
    for (const version of OVERRIDE_VERSIONS) {
      const entry = ValueModel.applyDdfOverride(row.ddfByVersion[COMPOSITE_VERSIONS[version]], override);
      if (override === null) continue;
      entry.confidenceNote = null;
      row.values[version] = entry.value;
    }
    row.valueOverride = override === null ? null : row.values.ddf_value;
    row.valueOverrideSpec = override === null ? null : { ...override };
    const { blended, charts, projections } = row.ddfByVersion;
    row.ddfPipelineValue = blended.pipelineValue;
    row.ddfCount = blended.count;
    row.ddfChartsCount = charts.count;
    row.ddfProjectionsCount = projections.count;
    row.ddfSources = [...blended.sources];
    row.ddfReason = blended.reason;
    row.ddfLowConfidence = blended.lowConfidence;
    row.ddfConfidenceNote = blended.confidenceNote;
    row.ddfChartsLowConfidence = charts.lowConfidence;
    row.ddfProjectionsLowConfidence = projections.lowConfidence;
    row.ddfPrior = null;
    row.ddfPriorCount = 0;
    row.ddfPriorLowConfidence = false;
    row.ddfTier = now.tier ?? null;
    row.lineupShare = Number.isFinite(now.lineupShare) ? now.lineupShare : null;
    row.startWorthy = Number.isFinite(now.startWorthy) ? now.startWorthy : null;
    return row;
  });
}

const rowCopy = (row: Any) => ({ ...row, values: { ...row.values }, ddfSources: [...(row.ddfSources || [])],
  missingReasons: { ...(row.missingReasons || {}) }, estimated: { ...(row.estimated || {}) },
  ddfByVersion: Object.fromEntries(Object.entries(row.ddfByVersion || {}).map(([v, e]: [string, Any]) => [v, { ...e, sources: [...e.sources] }])) });

/** A read-only TradeValueCurveControls: the getters find-engine, finder.ui, waivers, ddf-engine and ddf-league read. */
export function makeControls(o: { pipeline: Any; input: Any; rows: Any[]; shape: Record<string, number>; scoring: string;
  teams: number; week: number | null }): Any {
  const { pipeline, input, rows, shape } = o;
  const hidden = new Set<string>(input.hidden || []);
  const byKey = new Map(rows.map((r) => [r.player_key, r]));
  const available = (key: string) => {
    const source = seriesSource(key);
    if (!source || !pipeline.sources?.[source] || hidden.has(source)) return false;
    return rows.some((r) => Number.isFinite(r.values[key])) || Object.values(pipeline.rows || {}).some((r: Any) =>
      Number.isFinite(r[seriesField(key)]?.[source]));
  };
  const benchShare = input.setting?.bench_share_override ?? pipeline.benchShare?.overall ?? DEFAULT_BENCH_SHARE;
  const included = Object.keys(pipeline.sources || {}).filter((k) => !(pipeline.excluded || []).some((e: Any) => e.key === k));
  return {
    isReady: () => true,
    getState: () => ({ position: "ALL", scoring: o.scoring, teams: o.teams, model: "monday", valueMode: "indexed", viewMode: "indexed",
      lockOrder: "ddf_value", benchShare, absenceRate: benchShare, activeSources: VISIBLE_KEYS.filter(available) }),
    getRosterShape: () => ({ ...shape }),
    getAllRows: () => rows.map(rowCopy),
    getPlayer: (key: unknown) => { const r = byKey.get(Number(key)); return r ? rowCopy(r) : null; },
    getSourceInfo: () => VISIBLE_KEYS.map((key) => ({ key, available: available(key), active: available(key),
      included: included.includes(seriesSource(key) || key) })),
    getAdjustmentWeights: () => ({
      allocation: POSITION_ORDER.map((pos) => {
        const a = pipeline.slotFill?.[pos] || { dedicated: 0, superflex: 0, flex: 0, bench: 0, starters: 0, rostered: 0 };
        return { pos, direct: a.dedicated, superflex: a.superflex, flex: a.flex, bench: a.bench, lineup: a.starters, rostered: a.rostered };
      }),
      cells: [],
    }),
    getBenchShareReadout: () => {
      const r = pipeline.benchShare;
      if (!r) return null;
      const lineup = pipeline.lineup;
      return { QB: r.QB, RB: r.RB, WR: r.WR, TE: r.TE, overall: r.overall, override: r.override, overrideValue: r.overrideValue,
        fillInShare: r.fillInShare, method: r.method, contentWeek: lineup ? lineup.content_week : null,
        window: lineup && lineup.window ? [...lineup.window] : null, error: null };
    },
    getBenchShare: () => benchShare,
    getReferenceWeek: () => o.week,
    getBasis: () => null,
    getPriorWeek: () => Promise.resolve(null),
    // Settings are fixed for the request: ddf-engine only calls these when a saved setting or link differs (none here).
    setBasis: noop, setValueOverrides: noop, setScoring: noop, setTeams: noop, setRosterSpot: noop, setWeek: noop,
    setLineupSettings: noop, setPositionWeights: noop, setLeagueWeeks: noop,
  };
}

// ---------------------------------------------------------------------------------------------------------------------
// The request.
// ---------------------------------------------------------------------------------------------------------------------
export const MAX_OPPONENTS = 19;
export const MAX_KEYS = 60;
const REQUEST_KEYS = new Set(["league", "me", "opponents", "skipped", "sizes", "held", "ov", "min_bench", "alternatives", "why"]);
export const DEFAULT_ALTERNATIVES = 10;
const MAX_ALTERNATIVES = 500;
// Requests for source-level output: never served on the answers path.
const SOURCE_REQUEST = /^(include|basis|sources?|per_source|by_source|charts?|chart_keys|their_valuation|your_valuation|valuation|split)$/i;

export interface AnswersRequest {
  league: League;
  me: { index: number; keys: string[]; others: Array<{ pos: string; name: string }> };
  opponents: Array<{ id: string | number; name: string; keys: string[] }>;
  skipped: Array<string | number>;
  sizes: number[];
  held: string[];
  ov: string | null;
  minBench: Record<string, number>;
  /** How many of each group's alternatives (find.html's give select) the reply lists. */
  alternatives: number;
  /** Why mode: the Why panel of one trade (an alternative the reply lists without it). */
  why: { team: string | number; give: string[]; receive: string[] } | null;
}

export type Refusal = { status: number; code: string; error: string };
const refuse = (status: number, code: string, error: string): Refusal => ({ status, code, error });
const isId = (v: unknown) => (typeof v === "string" && v.length > 0 && v.length <= 64) || (Number.isInteger(v) && (v as number) >= 0);
const keyList = (v: unknown) => Array.isArray(v) && v.length <= MAX_KEYS && v.every((k) => Number.isInteger(Number(k)) && String(k).trim() !== "");

/** Read and check the POST body. Anything that asks for source-level output is refused, never ignored. */
export function parseRequest(body: unknown): { ok: true; req: AnswersRequest } | { ok: false; refusal: Refusal } {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { ok: false, refusal: refuse(400, "bad_request", "the body must be a JSON object") };
  const b = body as Record<string, Any>;
  for (const k of Object.keys(b)) {
    if (SOURCE_REQUEST.test(k)) {
      return { ok: false, refusal: refuse(400, "not_in_answers", `${k} is not available here: this endpoint returns DDF answers only, never source-level data`) };
    }
    if (!REQUEST_KEYS.has(k)) return { ok: false, refusal: refuse(400, "unknown_field", `unknown field: ${k}`) };
  }
  const league = b.league;
  if (!league || typeof league !== "object" || Array.isArray(league)) return { ok: false, refusal: refuse(400, "bad_league", "league must be an object (get-values' league shape)") };
  for (const k of Object.keys(league)) {
    if (SOURCE_REQUEST.test(k)) return { ok: false, refusal: refuse(400, "not_in_answers", `league.${k} is not available here: DDF answers only`) };
  }
  const me = b.me;
  if (!me || typeof me !== "object" || !keyList(me.keys)) return { ok: false, refusal: refuse(400, "bad_me", `me.keys must be a list of up to ${MAX_KEYS} player keys`) };
  const opponents = b.opponents;
  if (!Array.isArray(opponents) || !opponents.length || opponents.length > MAX_OPPONENTS) {
    return { ok: false, refusal: refuse(400, "bad_opponents", `opponents must list 1 to ${MAX_OPPONENTS} teams`) };
  }
  const ids = new Set<string>();
  for (const t of opponents) {
    if (!t || typeof t !== "object" || !isId(t.id) || typeof t.name !== "string" || t.name.length > 80 || !keyList(t.keys)) {
      return { ok: false, refusal: refuse(400, "bad_opponents", `each opponent is {id, name, keys} with up to ${MAX_KEYS} player keys`) };
    }
    if (ids.has(String(t.id))) return { ok: false, refusal: refuse(400, "bad_opponents", `duplicate opponent id ${t.id}`) };
    ids.add(String(t.id));
  }
  const index = me.index === undefined ? 0 : me.index;
  if (!Number.isInteger(index) || index < 0 || index > opponents.length) {
    return { ok: false, refusal: refuse(400, "bad_me", "me.index is my team's place in the league order (0 to the number of opponents)") };
  }
  const others = me.others === undefined ? [] : me.others;
  if (!Array.isArray(others) || others.length > 6 || !others.every((x: Any) => x && ["K", "DEF", "DST"].includes(x.pos) && typeof x.name === "string" && x.name.length <= 80)) {
    return { ok: false, refusal: refuse(400, "bad_me", "me.others lists up to 6 kickers / defenses as {pos, name}") };
  }
  const skipped = b.skipped === undefined ? [] : b.skipped;
  if (!Array.isArray(skipped) || !skipped.every((id: unknown) => isId(id) && ids.has(String(id)))) {
    return { ok: false, refusal: refuse(400, "bad_skipped", "skipped lists opponent ids") };
  }
  const sizes = b.sizes === undefined ? [1, 2] : b.sizes;
  if (!Array.isArray(sizes) || !sizes.length || !sizes.every((n: unknown) => n === 1 || n === 2) || new Set(sizes).size !== sizes.length) {
    return { ok: false, refusal: refuse(400, "bad_sizes", "sizes is a subset of [1, 2]: larger packages are not served here (CPU limit)") };
  }
  const held = b.held === undefined ? [] : b.held;
  if (!keyList(held)) return { ok: false, refusal: refuse(400, "bad_held", `held lists up to ${MAX_KEYS} player keys`) };
  const ov = b.ov === undefined || b.ov === null || b.ov === "" ? null : b.ov;
  if (ov !== null && typeof ov !== "string") return { ok: false, refusal: refuse(400, "bad_ov", "ov is the share link's ov= text") };
  const mb = b.min_bench === undefined ? {} : b.min_bench;
  const minBench: Record<string, number> = {};
  if (!mb || typeof mb !== "object" || Array.isArray(mb)) return { ok: false, refusal: refuse(400, "bad_min_bench", "min_bench is {QB, RB, WR, TE}") };
  for (const [k, v] of Object.entries(mb)) {
    if (!POSITION_ORDER.includes(k) || !Number.isInteger(v) || (v as number) < 0 || (v as number) > 10) {
      return { ok: false, refusal: refuse(400, "bad_min_bench", "min_bench is {QB, RB, WR, TE}, each 0-10") };
    }
    minBench[k] = v as number;
  }
  const alternatives = b.alternatives === undefined ? DEFAULT_ALTERNATIVES : b.alternatives;
  if (!Number.isInteger(alternatives) || alternatives < 1 || alternatives > MAX_ALTERNATIVES) {
    return { ok: false, refusal: refuse(400, "bad_alternatives", `alternatives is 1 to ${MAX_ALTERNATIVES}`) };
  }
  let why: AnswersRequest["why"] = null;
  if (b.why !== undefined && b.why !== null) {
    const w = b.why;
    const side = (v: unknown) => keyList(v) && (v as unknown[]).length >= 1 && (v as unknown[]).length <= 2;
    if (!w || typeof w !== "object" || !isId(w.team) || !ids.has(String(w.team)) || !side(w.give) || !side(w.receive)) {
      return { ok: false, refusal: refuse(400, "bad_why", "why is {team, give, receive}: an opponent id and 1-2 player keys each side") };
    }
    why = { team: w.team, give: w.give.map(String), receive: w.receive.map(String) };
  }
  return { ok: true, req: {
    league: league as League,
    me: { index, keys: me.keys.map(String), others: others.map((x: Any) => ({ pos: x.pos, name: x.name })) },
    opponents: opponents.map((t: Any) => ({ id: t.id, name: t.name, keys: t.keys.map(String) })),
    skipped, sizes: [...sizes].sort(), held: held.map(String), ov, minBench, alternatives, why,
  } };
}

// ---------------------------------------------------------------------------------------------------------------------
// The engine run (cached by the caller per league and week) and the answer.
// ---------------------------------------------------------------------------------------------------------------------
export interface Deps {
  bundle: Bundle & { lineupConfig: Any; history: Any; meta?: Any };
  valueLink: Any;
  scripts: CompiledScript[];
  today: string;
  /** Load one saved week's history document when the priced week needs it (get-values' loadHistoryDoc). */
  loadHistoryDoc?: (week: number) => Promise<void>;
  /** Engine runs kept by the caller: key -> {pipeline, input, mapped, plan}. */
  runs?: Map<string, Any>;
}

export async function engineRun(deps: Deps, league: League): Promise<{ ok: true; run: Any } | { ok: false; refusal: Refusal }> {
  const mapped = mapLeague(league, deps.bundle.lineupConfig as { defaults?: LineupDefaults; content_week?: number | null } | null);
  const plan = planWeek(deps.bundle, mapped, null, deps.today);
  if (!plan.ok) return { ok: false, refusal: refuse(400, "week_unavailable", plan.error) };
  const key = JSON.stringify([mapped.scoring, mapped.setting, mapped.lineupArgs, plan.week]);
  const hit = deps.runs?.get(key);
  if (hit) return { ok: true, run: hit };
  if (deps.loadHistoryDoc) {
    if (plan.docWeek !== null) await deps.loadHistoryDoc(plan.docWeek);
    if (Number.isInteger(plan.week)) await deps.loadHistoryDoc((plan.week as number) - 1);
  }
  const input = { ...buildPipelineInput(deps.bundle, mapped, plan), basisConfig: null };
  const pipeline = (deps.bundle.ValueModel as Any).runValuePipeline(input);
  const run = { key, mapped, plan, input, pipeline, canonical: canonicalPlayers(deps.bundle.players as Any[]) };
  deps.runs?.set(key, run);
  return { ok: true, run };
}

const r1 = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? Math.round(v * 10) / 10 : null);
const r2 = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? Math.round(v * 100) / 100 : null);
const keyOf = (r: Any) => String(r.player_key);
const keysOf = (rows: Any[]) => rows.map((r) => Number(r.player_key));

/** find-page.js sorter() for the default sort ("Your starter improvement"), on each group's shown trade (trades[0]). */
function pageOrder(a: Any, b: Any): number {
  const ta = a.trades[0] || a.best, tb = b.trades[0] || b.best, va = ta.you, vb = tb.you;
  if (va === null && vb !== null) return 1;
  if (vb === null && va !== null) return -1;
  return (vb || 0) - (va || 0) || tb.edge - ta.edge || tb.score - ta.score || a.partner.localeCompare(b.partner) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
}

export interface AnswerOptions { validate?: boolean }

/** The whole answer for one request. Returns the reply (validated against REPLY_SPEC unless validate is false). */
export async function answer(req: AnswersRequest, deps: Deps, opts: AnswerOptions = {}): Promise<{ status: number; body: Any }> {
  // Overrides: the share link's ov= text, read by the site's own link reader (get-values value-context.ts).
  let overrides: Record<string, unknown> = {};
  if (req.ov !== null) {
    if (!canReadStrictly(deps.valueLink)) return { status: 503, body: { error: "ov is not available yet: the site does not publish its link reader", code: "value_context_unavailable" } };
    const read = readValueContext(deps.valueLink, null, req.ov);
    // The link reader's own message can list source keys, so the refusal is worded here.
    if (!read.ok) return { status: read.status, body: { error: "ov could not be read: use the share link's ov= text (player_key:value or player_key:+delta, comma separated)", code: read.code } };
    overrides = read.context.overrides;
  }
  const er = await engineRun(deps, req.league);
  if (!er.ok) return { status: er.refusal.status, body: { error: er.refusal.error, code: er.refusal.code } };
  const run = er.run;
  const shape = rosterShapeOf(req.league, run.mapped);
  const rows = buildRows(deps.bundle.ValueModel, run.pipeline, run.canonical, overrides);
  const controls = makeControls({ pipeline: run.pipeline, input: run.input, rows, shape, scoring: run.mapped.scoring,
    teams: run.mapped.teams, week: run.plan.week ?? null });

  // The league as connect/setup stores it (sessionStorage ddf:pasted): my team at its place in the league order.
  const order: Array<{ id: string | number | null; name: string; keys: string[]; others?: Any[] }> =
    req.opponents.map((t) => ({ id: t.id, name: t.name, keys: t.keys }));
  order.splice(req.me.index, 0, { id: null, name: "My team", keys: req.me.keys, others: req.me.others });
  const pasted = { v: 1, source: "answers", me: req.me.index, teams: order.map((t) => ({ name: t.name,
    players: [...t.keys.map((k): Any => ({ key: k })), ...(t.others || []).map((x: Any): Any => ({ name: x.name, pos: x.pos, key: null }))] })) };
  const idOfIndex = (i: number) => order[i]?.id ?? null;
  const skippedNames = req.skipped.map((id) => order.find((t) => t.id !== null && String(t.id) === String(id))!.name);
  const win = makeWindow(controls, {
    "ddf:pasted": JSON.stringify(pasted),
    "ddf:skip": JSON.stringify(skippedNames),
    "ddf:hold": JSON.stringify(req.held),
  });
  runPageModules(deps.scripts, win);
  const DDF = win.DDF;
  await DDF.engine.ready;
  const cur = await DDF.league.ready;
  if (!cur || !DDF.league.myTeam()) return { status: 422, body: { error: "the league could not be read", code: "no_league" } };
  const me = DDF.league.myTeam();
  const ctx = DDF.find.context();
  if (!ctx) return { status: 503, body: { error: "the engine is not ready", code: "engine_unavailable" } };

  // find-page.js run(): partners, waiver pickups (the waiver alternative's pool), then each partner's search.
  const skip = new Set(DDF.league.skipped());
  const list = DDF.league.opponents().filter((t: Any) => !skip.has(t.name) && DDF.find.rowsOf(t).length > 0);
  const availableEntries = (cur.waivers || []).map((r: Any) => ({ key: r.key, name: r.n, pos: r.pos, team: r.team }));
  const pickups = availableEntries.length ? DDF.find.pickups(ctx, DDF.find.entriesOf(me), availableEntries, "DDF") : null;
  const rostered = new Set<string>();
  (cur.teams || []).forEach((t: Any) => DDF.find.rowsOf(t).forEach((r: Any) => rostered.add(keyOf(r))));
  const gainOf = (r: Any) => Math.round(r.starterDelta * 10) / 10;
  const waiverPool = (pickups ? pickups.results : []).filter((r: Any) => r.starterDelta !== null && gainOf(r) > 0 && !rostered.has(keyOf(r.candidate)))
    .map((r: Any) => ({ row: r.candidate, starterDelta: r.starterDelta }));
  const held = new Set<string>(DDF.league.held().map(String));
  const mine = DDF.find.rowsOf(me);
  const searchOpts = { your: "DDF", their: "Market", sizes: req.sizes, minBench: { QB: 0, RB: 0, WR: 0, TE: 0, ...req.minBench }, held, waivers: waiverPool };
  const groups: Any[] = [];
  const notes = { sanity: 0, guardrail: 0, partial: [] as Any[], unjudged: false, searchedTop: false };
  // Why mode: one partner's search, for the one trade asked about.
  const partnersSearched = req.why ? list.filter((t: Any) => String(idOfIndex(t.index)) === String(req.why!.team)) : list;
  for (const team of partnersSearched) {
    const theirRows = DDF.find.rowsOf(team);
    const res = DDF.find.searchPartner(ctx, mine, theirRows, searchOpts);
    notes.sanity += res.sanityDropped;
    notes.guardrail += res.guardrailDropped;
    if (res.partial) notes.partial.push(idOfIndex(team.index));
    if (!res.judged) notes.unjudged = true;
    if (res.searched.mine.searched < res.searched.mine.of || res.searched.theirs.searched < res.searched.theirs.of) notes.searchedTop = true;
    DDF.find.group(res.trades, searchOpts).forEach((g: Any) => {
      groups.push(Object.assign(g, { partner: team.name, partnerIndex: team.index, id: team.index + "|" + g.cls + "|" + g.key, mineRows: mine, theirRows }));
    });
  }

  // The Why panel exactly as find-page.js whyFill() fills it (DDFWhy.explain on the card's rows and valuations).
  const whyCtx = Object.assign({}, ctx, { ourKey: DDF.find.valuation("DDF").key, marketKey: DDF.find.valuation("Market").key });
  const whyOf = (g: Any, t: Any) => {
    const e = t.fit && win.DDFWhy ? win.DDFWhy.explain({ mine: g.mineRows, theirs: g.theirRows, give: t.give, receive: t.receive, waiver: t.waiver || null }, whyCtx) : null;
    if (!e) return null;
    return {
      natural: Boolean(e.natural), headline: String(e.headline),
      give: e.you.leaving.map((x: Any) => ({ key: Number(x.row.player_key), role: roleOf(x, true) })),
      get: e.you.arriving.map((x: Any) => ({ key: Number(x.row.player_key), role: roleOf(x, false) })),
      net: String(e.table.net),
      reasons: e.reasons.map((r: Any) => ({ kind: String(r.kind), text: String(r.text) })),
      their_sentence: e.pct ? String(e.pct.sentence || "") : "",
      you: { starters: r1(e.you.starterDelta), bench: r1(e.you.benchDelta), net: r1(e.you.net),
        by_position: Object.fromEntries(POSITION_ORDER.map((pos) => [pos, r1(e.you.posDelta[pos])])) },
    };
  };
  // The roster percents the Why panel heads with (ddf-why.js pct(): DDFOpportunity.rosterImprovementPct on the same
  // rows and keys), for every trade, so a card shows them for any alternative without its Why.
  const pctOf = (g: Any, t: Any) => {
    const O = win.DDFOpportunity, k = whyCtx;
    if (!t.fit || !ctx.shape || !ctx.expected || !ctx.analyst) return null;   // ddf-why explain(): not judged, no percent
    const octx = Object.assign({}, k, { senderKey: k.ourKey, partnerKey: k.marketKey, chartKeys: ctx.analyst || undefined });
    const trade = { mine: g.mineRows, theirs: g.theirRows, give: t.give, receive: t.receive };
    const sp = O.rosterImprovementPct(trade, "sender", octx), pp = O.rosterImprovementPct(trade, "partner", octx);
    const fin = Number.isFinite;
    if (!sp || !pp || !fin(sp.pct) || !fin(pp.pct) || !fin(sp.shown) || !fin(pp.shown) || !BANDS.includes(pp.band)) return null;
    return { you: sp.shown, them: { band: pp.band, pct: pp.shown } };
  };
  const tradeOut = (g: Any, t: Any) => {
    const p = pctOf(g, t);
    return {
      give: keysOf(t.give), receive: keysOf(t.receive), edge: r1(t.edge), starters: r1(t.you),
      roster_pct: p ? p.you : null, them: p ? p.them : null,
      waiver: t.waiver ? { players: t.waiver.players.map((x: Any) => Number(x.key)), covered: r2(t.waiver.covered), demoted: Boolean(t.waiver.demoted),
        // The card's note (find-page.js card()): only on a demoted offer.
        line: t.waiver.demoted ? (win.DDFWhy.waiverLine(t.waiver, t.give) || "") : "" } : null,
      added: (t.addedThrowIns || []).map((a: Any) => ({ key: Number(a.row.player_key), side: a.side === "give" ? "give" : "receive" })),
      also: t.throwIns ? keysOf(t.throwIns.give.concat(t.throwIns.receive)) : [],
      unbalanced: Boolean(t.unbalanced),
    };
  };

  if (req.why) {
    const same = (a: number[], b: string[]) => a.length === b.length && a.map(String).sort().join() === [...b].sort().join();
    let hit: Any = null;
    for (const g of groups) for (const t of g.trades) if (!hit && same(keysOf(t.give), req.why.give) && same(keysOf(t.receive), req.why.receive)) hit = { g, t };
    const body = hit
      ? { v: 1, found: true, team: idOfIndex(hit.g.partnerIndex), fit: hit.g.cls, trade: tradeOut(hit.g, hit.t), why: whyOf(hit.g, hit.t) }
      : { v: 1, found: false, team: req.why.team, fit: null, trade: null, why: null };
    return finish(body, WHY_REPLY_SPEC, opts);
  }

  // find-page.js visible(): natural, then partner neutral followed by unjudged, then force fits; each in the page order.
  const cls = (c: string) => groups.filter((g) => g.cls === c).sort(pageOrder);
  const sections = { natural: cls("natural"), neutral: cls("neutral").concat(cls("unjudged")), force: cls("force") };
  // Each group lists its alternatives in the page's order (the card's select), the first `alternatives` of them. The Why
  // panel is one more call per trade (req.why), as the page fills it on first open (find-page.js whyFill).
  const groupOut = (g: Any) => ({ team: idOfIndex(g.partnerIndex), fit: g.cls, receive: g.key.split(",").map(Number),
    alternatives: g.trades.length, trades: g.trades.slice(0, req.alternatives).map((t: Any) => tradeOut(g, t)) });

  // Partner order (ddf-league.js partnerRank, partners.html): DDF score, ties by the Analyst-charts ratio here (D4).
  const partners = DDF.league.partnerRank().map((p: Any) => ({ team: idOfIndex(p.index), rank: p.rank, score: r2(p.score),
    get: p.get.map((x: Any) => x.pos), give: p.give.map((x: Any) => x.pos), two_way: Boolean(p.twoWay) }));
  // Opportunity tier (team.html: DDFOpportunity.computeTeam on the find.html searches and the Waivers tab's pickups).
  const o = await win.DDFOpportunity.computeTeam(cur, me);
  const team = o ? { tier: o.tier, reason: o.reason ?? null, pct: Number.isFinite(o.shown) ? o.shown : null, gain: r1(o.gain),
    source: o.source ?? null, headline: String(o.headline), line: String(o.line),
    trade_team: o.trade && Number.isInteger(o.trade.partner) && o.source === "trade" ? idOfIndex(o.trade.partner) : null } : null;

  const body = {
    v: 1,
    as_of: (deps.bundle.meta && typeof deps.bundle.meta.as_of === "string") ? deps.bundle.meta.as_of : null,
    week: Number.isInteger(run.plan.week) ? run.plan.week : null,
    setting: { scoring: run.mapped.scoring, teams: run.mapped.teams, superflex: run.mapped.setting.superflex },
    sizes: req.sizes,
    team,
    partners,
    natural: sections.natural.map(groupOut),
    neutral: sections.neutral.map(groupOut),
    force: sections.force.map(groupOut),
    notes: { searched: list.map((t: Any) => idOfIndex(t.index)), sanity_dropped: notes.sanity, guardrail_dropped: notes.guardrail,
      partial: notes.partial, unjudged: notes.unjudged, searched_top: notes.searchedTop, held: held.size,
      overrides: Object.keys(overrides).length },
  };
  return finish(body, REPLY_SPEC, opts);
}

function finish(body: Any, spec: Spec, opts: AnswerOptions): { status: number; body: Any } {
  if (opts.validate !== false) {
    const problems = validateReply(body, spec);
    if (problems.length) return { status: 500, body: { error: "the reply failed the answers allowlist and was not sent", code: "reply_not_allowed", problems: problems.slice(0, 5) } };
  }
  return { status: 200, body };
}

// ddf-why.js role() / roleBefore() words for the table ("starts at QB", "bench", "no value yet").
function roleOf(x: Any, before: boolean): string {
  if (x.slot) return before ? "a starter at " + x.slot : "starts at " + x.slot;
  return x.valued ? "bench" : "no value yet";
}

// ---------------------------------------------------------------------------------------------------------------------
// The reply allowlist. Every key and type is listed; anything else fails. Then the answers privacy text check.
// ---------------------------------------------------------------------------------------------------------------------
type Spec = string | { obj: Record<string, Spec> } | { arr: Spec } | { nul: Spec } | { enum: Array<string | number> } | { map: Spec; keys: string[] };
const KEY: Spec = "int";
const ID: Spec = "id";
const WORDS_TIER = { enum: ["big", "medium", "marginal", "none"] };
const FIT = { enum: ["natural", "neutral", "force", "unjudged"] };
const BANDS = ["better", "unchanged", "slightly_worse", "clearly_worse"];
const BAND = { enum: BANDS };
const TRADE: Spec = { obj: {
  give: { arr: KEY }, receive: { arr: KEY }, edge: "num", starters: { nul: "num" }, roster_pct: { nul: "num" },
  them: { nul: { obj: { band: BAND, pct: "num" } } },
  waiver: { nul: { obj: { players: { arr: KEY }, covered: { nul: "num" }, demoted: "bool", line: "str" } } },
  added: { arr: { obj: { key: KEY, side: { enum: ["give", "receive"] } } } }, also: { arr: KEY }, unbalanced: "bool",
} };
const WHY: Spec = { nul: { obj: {
  natural: "bool", headline: "str", give: { arr: { obj: { key: KEY, role: "str" } } }, get: { arr: { obj: { key: KEY, role: "str" } } },
  net: "str", reasons: { arr: { obj: { kind: "str", text: "str" } } }, their_sentence: "str",
  you: { obj: { starters: { nul: "num" }, bench: { nul: "num" }, net: { nul: "num" }, by_position: { map: { nul: "num" }, keys: POSITION_ORDER } } },
} } };
const GROUP: Spec = { obj: { team: ID, fit: FIT, receive: { arr: KEY }, alternatives: "int", trades: { arr: TRADE } } };
export const WHY_REPLY_SPEC: Spec = { obj: { v: "int", found: "bool", team: ID, fit: { nul: FIT }, trade: { nul: TRADE }, why: WHY } };
export const REPLY_SPEC: Spec = { obj: {
  v: "int", as_of: { nul: "str" }, week: { nul: "int" },
  setting: { obj: { scoring: { enum: ["standard", "half_ppr", "ppr"] }, teams: "int", superflex: "int" } },
  sizes: { arr: { enum: [1, 2] } },
  team: { nul: { obj: { tier: WORDS_TIER, reason: { nul: { enum: ["unsized", "unchecked", "small", "sharp"] } }, pct: { nul: "num" }, gain: { nul: "num" },
    source: { nul: { enum: ["trade", "waiver"] } }, headline: "str", line: "str", trade_team: { nul: ID } } } },
  partners: { arr: { obj: { team: ID, rank: "int", score: { nul: "num" }, get: { arr: { enum: POSITION_ORDER } }, give: { arr: { enum: POSITION_ORDER } }, two_way: "bool" } } },
  natural: { arr: GROUP }, neutral: { arr: GROUP }, force: { arr: GROUP },
  notes: { obj: { searched: { arr: ID }, sanity_dropped: "int", guardrail_dropped: "int", partial: { arr: ID }, unjudged: "bool",
    searched_top: "bool", held: "int", overrides: "int" } },
} };

// pipelines/answers_privacy.py BANNED (tests/test_get_answers.py checks the two lists agree) and its 3+ decimals rule.
export const BANNED = [
  "cbs", "usa\\s*today", "usatoday", "fantasy\\s*pros", "fantasy\\s*calc", "razzball", "mike\\s+clay",
  "espn",
  "analyst\\s+charts?", "live\\s+market", "trade\\s+charts?", "chart_values", "chart_indexed",
  "published\\s+values?", "players-data", "methodology-data", "comparison-sources", "reindex",
  "source_provenance", "sources_included", "sources_excluded", "missing_sources", "basis_members",
];
const BANNED_RE = new RegExp(BANNED.map((p) => `(?:${p})`).join("|"), "i");
const LONG_DECIMAL = /(?<![\w.])\d+\.\d{3,}(?![\w.])/;

function check(v: unknown, spec: Spec, path: string, out: string[]): void {
  if (out.length > 20) return;
  if (typeof spec === "string") {
    const ok = spec === "num" ? typeof v === "number" && Number.isFinite(v)
      : spec === "int" ? Number.isInteger(v)
      : spec === "str" ? typeof v === "string" && v.length <= 600
      : spec === "bool" ? typeof v === "boolean"
      : spec === "id" ? isId(v) : false;
    if (!ok) out.push(`${path}: expected ${spec}, got ${JSON.stringify(v)?.slice(0, 40)}`);
    return;
  }
  if ("nul" in spec) { if (v !== null) check(v, spec.nul, path, out); return; }
  if ("enum" in spec) { if (!spec.enum.includes(v as string)) out.push(`${path}: ${JSON.stringify(v)} is not one of ${spec.enum.join("/")}`); return; }
  if ("arr" in spec) {
    if (!Array.isArray(v)) { out.push(`${path}: expected a list`); return; }
    v.forEach((x, i) => check(x, spec.arr, `${path}[${i}]`, out));
    return;
  }
  if (!v || typeof v !== "object" || Array.isArray(v)) { out.push(`${path}: expected an object`); return; }
  const allowed = "map" in spec ? spec.keys : Object.keys(spec.obj);
  for (const k of Object.keys(v)) if (!allowed.includes(k)) out.push(`${path}.${k}: not in the allowlist`);
  for (const k of allowed) {
    if (!(k in (v as Record<string, unknown>))) { out.push(`${path}.${k}: missing`); continue; }
    check((v as Record<string, unknown>)[k], "map" in spec ? spec.map : spec.obj[k], `${path}.${k}`, out);
  }
}

/** Every problem with a reply: keys or types outside REPLY_SPEC, banned source text, or numbers with 3+ decimals. */
export function validateReply(body: unknown, spec: Spec = REPLY_SPEC): string[] {
  const out: string[] = [];
  check(body, spec, "reply", out);
  const text = JSON.stringify(body);
  const banned = BANNED_RE.exec(text);
  if (banned) out.push(`reply: banned text ${JSON.stringify(banned[0])} at ${banned.index}`);
  const long = LONG_DECIMAL.exec(text);
  if (long) out.push(`reply: number with 3+ decimals ${long[0]}`);
  return out;
}
