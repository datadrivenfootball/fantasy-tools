// Connector walkthrough 2026-11-21 (Jeremy: "Do all recommendations"): league entry for the chat tools.
// - slots in plain words (array, {QB:1,...} or Yahoo's slot string) become the state's league.roster;
// - a team count from 4 to 20 is priced at the nearest count the values support, and says so;
// - league_paste (raw Yahoo, ESPN or Sleeper text) is read by the site's own paste reader
//   (v2/roster-paste.js + next/rosterparse.js + next/league-paste.js, loaded by index.ts);
// - league_teams + my_team stand on their own: your roster and the opponents come from them.
// Pure functions, no Deno APIs.
import { splitNames } from "./names.ts";

export class LeagueInputError extends Error {}

export const PRICED_TEAMS = [8, 10, 12, 14];
export const MIN_TEAMS = 4;
export const MAX_TEAMS = 20;

/** The supported count nearest to n (a tie goes to the larger league). */
export function nearestTeams(n: number): number {
  return PRICED_TEAMS.reduce((best, t) => (Math.abs(t - n) < Math.abs(best - n) || (Math.abs(t - n) === Math.abs(best - n) && t > best) ? t : best));
}

export interface Roster {
  QB?: number;
  RB?: number;
  WR?: number;
  TE?: number;
  FLEX?: number;
  SUPERFLEX?: number;
  BENCH?: number;
}

// Slot labels as leagues print them. K, DEF and IR slots are read and left out: the values hold no kickers or defenses.
const SLOT_WORDS: Record<string, keyof Roster | "skip"> = {
  QB: "QB", RB: "RB", WR: "WR", TE: "TE",
  FLEX: "FLEX", "W/R/T": "FLEX", "RB/WR/TE": "FLEX", "WR/RB/TE": "FLEX", "W/R": "FLEX", "R/W/T": "FLEX", "W/T": "FLEX", "RB/WR": "FLEX", "WR/TE": "FLEX",
  SUPERFLEX: "SUPERFLEX", SF: "SUPERFLEX", "Q/W/R/T": "SUPERFLEX", "QB/RB/WR/TE": "SUPERFLEX", OP: "SUPERFLEX", "SUPER FLEX": "SUPERFLEX", SFLEX: "SUPERFLEX",
  BN: "BENCH", BE: "BENCH", BENCH: "BENCH",
  K: "skip", PK: "skip", DEF: "skip", DST: "skip", "D/ST": "skip", D: "skip", IR: "skip", "IR+": "skip", IDP: "skip", DL: "skip", LB: "skip", DB: "skip",
};
const ARRAY_ORDER: Array<keyof Roster> = ["QB", "RB", "WR", "TE", "FLEX", "BENCH"];

function slotCount(v: unknown, label: string): number {
  const n = typeof v === "number" ? v : Number(String(v).trim());
  if (!Number.isInteger(n) || n < 0 || n > 20) throw new LeagueInputError(`slots: ${label} must be a whole number from 0 to 20 (got ${JSON.stringify(v)}).`);
  return n;
}

function slotKey(word: string): keyof Roster | "skip" | null {
  const w = word.trim().toUpperCase().replace(/\s+/g, " ");
  return SLOT_WORDS[w] ?? SLOT_WORDS[w.replace(/\s/g, "")] ?? null;
}

/**
 * Roster slots in any of three forms: [QB, RB, WR, TE, FLEX, BENCH] (the older connector's array; a 7th number is
 * SUPERFLEX), {QB:1, RB:2, WR:3, TE:1, FLEX:1, K:1, DEF:1, BN:5}, or a slot string ("QB, RB, RB, WR, WR, WR, TE,
 * W/R/T, K, DEF, BN, BN" or "QB 1, RB 2, BN 5"). Returns null when no slots were given.
 */
export function parseSlots(raw: unknown): Roster | null {
  if (raw === undefined || raw === null || raw === "") return null;
  const out: Roster = {};
  const add = (k: keyof Roster, n: number) => { out[k] = (out[k] ?? 0) + n; };
  if (Array.isArray(raw)) {
    if (raw.length < 6 || raw.length > 7) throw new LeagueInputError("slots as a list must be [QB, RB, WR, TE, FLEX, BENCH] (6 numbers), or name each slot: {QB: 1, RB: 2, ...}.");
    raw.forEach((v, i) => add(i < 6 ? ARRAY_ORDER[i] : "SUPERFLEX", slotCount(v, i < 6 ? ARRAY_ORDER[i] : "SUPERFLEX")));
    return out;
  }
  if (typeof raw === "object") {
    for (const [label, v] of Object.entries(raw as Record<string, unknown>)) {
      const k = slotKey(label);
      if (!k) throw new LeagueInputError(`slots: unknown slot ${JSON.stringify(label)}. Use QB, RB, WR, TE, FLEX, SUPERFLEX, K, DEF or BN.`);
      const n = slotCount(v, label);
      if (k !== "skip") add(k, n);
    }
    return out;
  }
  const words = String(raw).split(/[,;\n]+/).map((w) => w.trim()).filter(Boolean);
  if (!words.length) return null;
  for (const word of words) {
    // "WR 3", "WR x3", "3 WR", "BN (5)" or a bare label counted once.
    const m = /^(.+?)\s*(?:[x×:=(]\s*)?(\d+)\)?$/i.exec(word) ?? /^(\d+)\s*[x×]?\s*(.+)$/i.exec(word);
    let label = word;
    let n = 1;
    if (m) {
      const numFirst = /^\d/.test(m[1]);
      label = numFirst ? m[2] : m[1];
      n = slotCount(numFirst ? m[1] : m[2], label);
    }
    const k = slotKey(label);
    if (!k) throw new LeagueInputError(`slots: unknown slot ${JSON.stringify(label)}. Use QB, RB, WR, TE, W/R/T (flex), Q/W/R/T or OP (superflex), K, DEF or BN.`);
    if (k !== "skip") add(k, n);
  }
  return out;
}

/** The finder's lineup shape from roster slots (missing slots keep the finder's defaults). */
export function shapeFromRoster(r: Roster | null | undefined): Record<string, number> | undefined {
  if (!r) return undefined;
  const shape: Record<string, number> = {};
  for (const k of ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"] as const) if (r[k] !== undefined) shape[k] = r[k]!;
  return Object.keys(shape).length ? shape : undefined;
}

// ---------- league rosters ----------

export interface PasteTeam {
  name: string;
  players: Array<{ name: string; key: string; pos: string }>;
  unmatched: Array<{ line: string; reason: string; pos?: string; options?: Array<{ name: string; pos: string }> }>;
}

export interface PasteResult {
  ok: boolean;
  reason?: string | null;
  teams: PasteTeam[];
}

/** The site's DDF.leaguePaste (next/league-paste.js) as index.ts loads it. */
export interface PasteReader {
  read(text: string, rows: Array<{ player_key: number; name: string; pos: string }>, opts?: Record<string, unknown>): PasteResult;
}

/** One league team as the tools use it: a name and the names (or keys) on its roster. */
export interface LeagueTeamInput {
  name: string;
  players: string[];
  /** Player keys the paste reader already matched (same order as players), when known. */
  keys?: Array<string | null>;
}

export interface LeagueRead {
  teams: LeagueTeamInput[];
  /** Index of the user's team in teams, or null when my_team was not given. */
  mine: number | null;
  notes: string[];
}

const MAX_LEAGUE_TEAMS = 20;

function teamIndex(teams: LeagueTeamInput[], raw: unknown, field: string): number | null {
  if (raw === undefined || raw === null || raw === "") return null;
  const names = teams.map((t) => t.name);
  const list = `Teams: ${names.map((n, i) => `${i} ${n}`).join(", ")}.`;
  if (typeof raw === "number") {
    if (!Number.isInteger(raw) || raw < 0 || raw >= teams.length) throw new LeagueInputError(`${field}: no team at index ${raw} (0-based). ${list}`);
    return raw;
  }
  const want = String(raw).trim().toLowerCase().replace(/\s+/g, " ");
  const exact = names.findIndex((n) => n.toLowerCase().replace(/\s+/g, " ") === want);
  if (exact >= 0) return exact;
  if (/^\d+$/.test(want)) return teamIndex(teams, Number(want), field);
  const partial = names.map((n, i) => [n, i] as const).filter(([n]) => n.toLowerCase().includes(want));
  if (partial.length === 1) return partial[0][1];
  throw new LeagueInputError(`${field}: ${partial.length ? "more than one team fits" : "no team named"} ${JSON.stringify(String(raw))}. ${list}`);
}

function teamsFromArg(raw: unknown): LeagueTeamInput[] {
  if (!Array.isArray(raw)) throw new LeagueInputError("league_teams must be a list of {name, players}.");
  if (raw.length > MAX_LEAGUE_TEAMS) throw new LeagueInputError(`league_teams: at most ${MAX_LEAGUE_TEAMS} teams.`);
  return raw.map((t, i) => {
    if (!t || typeof t !== "object" || Array.isArray(t)) throw new LeagueInputError(`league_teams[${i}] must be {name, players}.`);
    const row = t as Record<string, unknown>;
    const name = String(row.name ?? "").trim() || `Team ${i + 1}`;
    const players = Array.isArray(row.players) ? row.players.flatMap((p) => splitNames(p)) : splitNames(row.players ?? row.roster);
    return { name, players };
  });
}

/** K and DEF lines, folded into one count. */
export function kdefLine(kickers: number, defenses: number): string {
  if (!kickers && !defenses) return "";
  const part = (n: number, one: string, many: string) => (n ? `${n} ${n === 1 ? one : many}` : "");
  return `Left out: ${[part(kickers, "kicker", "kickers"), part(defenses, "defense", "defenses")].filter(Boolean).join(" and ")} (not valued).`;
}

/**
 * The league from league_paste (read by the site's paste reader) or league_teams, with my_team marking the user's.
 * Returns null when neither was given. `rows` are the priced players the paste reader matches against.
 */
export function readLeague(
  args: Record<string, unknown>,
  rows: Array<{ player_key: number; name: string; pos: string }>,
  paste: PasteReader | null,
): LeagueRead | null {
  const notes: string[] = [];
  let teams: LeagueTeamInput[] | null = null;
  if (typeof args.league_paste === "string" && args.league_paste.trim()) {
    if (!paste) throw new LeagueInputError("The league paste reader is unavailable right now. Give league_teams as [{name, players}] instead, or try again shortly.");
    const res = paste.read(args.league_paste, rows, {});
    if (!res || !res.ok || !res.teams?.length) {
      const why = res?.reason === "one-team" ? "it found only one team" : res?.reason === "empty" ? "it is empty" : "no teams could be read";
      throw new LeagueInputError(`league_paste: ${why}. Paste each team's name on its own line followed by its players, one per line.`);
    }
    let kickers = 0;
    let defenses = 0;
    const missing: string[] = [];
    teams = res.teams.slice(0, MAX_LEAGUE_TEAMS).map((t) => {
      const players: string[] = [];
      const keys: Array<string | null> = [];
      for (const p of t.players) { players.push(p.name); keys.push(p.key); }
      for (const u of t.unmatched) {
        if (u.reason === "kdef") { if (u.pos === "K") kickers++; else defenses++; continue; }
        // A line the reader could not pin to one player goes on by name: the tool's own matcher reports it.
        players.push(u.line);
        keys.push(null);
        if (u.reason === "look" && u.options?.length) missing.push(`${t.name}: "${u.line}" could be ${u.options.map((o) => `${o.name} (${o.pos})`).join(", ")}`);
      }
      return { name: t.name, players, keys };
    });
    if (res.teams.length > MAX_LEAGUE_TEAMS) notes.push(`Only the first ${MAX_LEAGUE_TEAMS} teams were read.`);
    notes.push(`Read ${teams.length} teams from the paste: ${teams.map((t) => `${t.name} (${t.players.length})`).join(", ")}.`);
    const kd = kdefLine(kickers, defenses);
    if (kd) notes.push(kd);
    notes.push(...missing);
  } else if (args.league_teams !== undefined && args.league_teams !== null) {
    teams = teamsFromArg(args.league_teams);
  }
  if (!teams) {
    if (args.my_team !== undefined && args.my_team !== null && args.my_team !== "") {
      throw new LeagueInputError("my_team needs the league: give league_paste or league_teams too.");
    }
    return null;
  }
  if (teams.length < 2) throw new LeagueInputError("The league needs at least two teams.");
  return { teams, mine: teamIndex(teams, args.my_team, "my_team"), notes };
}

/** The partner team for find_trades: their_team, or the only other team. */
export function partnerIndex(league: LeagueRead, raw: unknown): number {
  const i = teamIndex(league.teams, raw, "their_team");
  if (i !== null) {
    if (i === league.mine) throw new LeagueInputError("their_team is your own team. Pick another team.");
    return i;
  }
  const others = league.teams.map((_, j) => j).filter((j) => j !== league.mine);
  if (others.length === 1) return others[0];
  throw new LeagueInputError(`find_trades needs their_team (a team name or 0-based index), or use find_trades_league for every team. Teams: ${league.teams.map((t, j) => `${j} ${t.name}`).join(", ")}.`);
}

/** League teams as the state stores them: {name, players: [{key, name}]}. */
export function stateTeams(league: LeagueRead, entry: (input: string, key: string | null) => { key?: string; name: string }) {
  return league.teams.map((t) => ({ name: t.name.slice(0, 60), players: t.players.map((n, i) => entry(n, t.keys?.[i] ?? null)) }));
}

/** The site files the paste reader needs, in load order (index.ts fetches them from the site origin). */
export const PASTE_FILES = ["v2/kdef-names.js", "v2/roster-paste.js", "next/rosterparse.js", "next/league-paste.js"];

/**
 * Evaluate the site's paste reader files in one sandbox window, as the page loads them. Returns the reader (null when
 * it did not load) and the kicker names from kdef-names.js (empty when that file is missing).
 */
export function evalPasteReader(sources: Array<string | null>): { reader: PasteReader | null; kickers: string[] } {
  // deno-lint-ignore no-explicit-any
  const sandbox: any = { addEventListener() {}, removeEventListener() {} };
  sources.forEach((source, i) => {
    if (!source) return;
    try {
      // A body without `module` in scope, so a module's CommonJS branch is skipped and it publishes on the window.
      new Function("window", "globalThis", "self", source)(sandbox, sandbox, sandbox);
    } catch (e) {
      console.error(`${PASTE_FILES[i] ?? "paste file"} threw while loading:`, String((e as Error)?.message ?? e));
    }
  });
  const api = sandbox.DDF?.leaguePaste;
  const kickers = ((sandbox.TradeValueKDef?.kickers ?? []) as Array<{ name?: string }>).map((k) => String(k?.name ?? "")).filter(Boolean);
  return { reader: api && typeof api.read === "function" && sandbox.DDFRosterPaste ? api as PasteReader : null, kickers };
}
