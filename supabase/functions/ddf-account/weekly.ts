// Player weekly projections for a stored league (JEG-1736): GET /leagues/:id/weekly -> ddf-league-weekly/0.
// Weekly scoring only, never DDF Value. Missing is never 0: a cell nothing gave is null with a note.
//  - QB/RB/WR/TE: the weekly projection warehouse (JEG-1641), latest run per source; ESPN first (stored
//    points_<scoring>), Sleeper where ESPN has no row.
//  - K/DEF: not in the warehouse, so ESPN's own weekly projection, read live (one request, every week).
//  - Identity by ID: Yahoo id -> Sleeper player DB / Dynasty Daddy `yahoo_id` -> sleeper_id, espn_id.
//    K and DEF have no Yahoo id in either; DEF joins on the NFL team (one D/ST per team), K on team + position
//    (+ last name if a team has two). Those joins are marked `match` so a page can say so.
//  - Byes from the nflverse schedule (latest run): bye = true, points 0, shown as BYE.
import { getJSON, type Fetch } from "./errors.ts";
import { PRO_TEAM } from "./espn.ts";
import { leagueRules, rescore, rulesNotes } from "./scoring.ts";

// deno-lint-ignore no-explicit-any
type J = any;
export type WarehouseRow = {
  source: "espn" | "sleeper"; as_of: string; target_week: number; source_player_id: string; sleeper_id: string | null;
  team: string | null; position: string | null; points_std: number | null; points_half_ppr: number | null; points_ppr: number | null;
  stats?: Record<string, number> | null;
};
export type ScheduleGame = { week: number; home_team: string; away_team: string; as_of: string; gameday?: string | null; gametime?: string | null };
export type XwalkRow = [sleeper: string | null, espn: string | null, yahoo: string | null, name: string, pos: string | null, team: string | null];
export type KdefRow = { espn_id: string; name: string; pos: "K" | "DEF"; team: string | null; weeks: Record<string, number>; lines?: Record<string, Record<string, number>> };
export type WeeklyDeps = {
  rows: (season: number, fromWeek: number, espnIds: string[], sleeperIds: string[]) => Promise<WarehouseRow[]>;
  schedule: (season: number) => Promise<ScheduleGame[]>;
  xwalk: () => Promise<XwalkRow[]>;
  kdef: (season: number) => Promise<{ as_of: string; players: KdefRow[] } | null>;
};
export type Cell = { points: number | null; source: "espn" | "sleeper" | "espn_live" | null; bye: boolean; note: string | null; rescored?: boolean };

const SKILL = new Set(["QB", "RB", "WR", "TE"]);
// nflverse codes; Yahoo/Sleeper/ESPN spellings mapped onto them.
const TEAM_ALIAS: Record<string, string> = { LAR: "LA", JAC: "JAX", WSH: "WAS", "LA RAMS": "LA" };
export const teamCode = (t: unknown) => {
  const s = typeof t === "string" ? t.trim().toUpperCase() : "";
  return s ? (TEAM_ALIAS[s] || s) : null;
};
const posOf = (p: J) => {
  const s = String(p?.position ?? "").toUpperCase();
  return s === "DST" || s === "D/ST" || s === "DEF" ? "DEF" : s || null;
};
const lastName = (n: string) => n.toLowerCase().replace(/\b(jr|sr|ii|iii|iv)\.?$/g, "").trim().split(/\s+/).pop() || "";
const yahooNum = (id: string) => /\.p\.(\d+)$/.exec(id)?.[1] ?? (/^\d+$/.test(id) ? id : null);
const pointsCol = (scoring: string) => (scoring === "ppr" ? "points_ppr" : scoring === "standard" ? "points_std" : "points_half_ppr");
const num = (x: unknown) => (x === null || x === undefined || x === "" ? null : Number.isFinite(Number(x)) ? Number(x) : null);

export function leagueWeeks(summary: J): number[] {
  const cur = num(summary?.current_week) ?? 1;
  const st = summary?.settings || {};
  const fromSched = (summary?.schedule || []).map((w: J) => num(w.week)).filter((w: number | null): w is number => w !== null);
  let last = Math.max(0, ...fromSched);
  const start = num(st.playoff_start_week), spots = num(st.playoff_teams);
  if (start && spots) {
    const rounds = spots <= 2 ? 1 : spots <= 4 ? 2 : spots <= 8 ? 3 : 4;
    last = Math.max(last, start + rounds - 1);
  }
  last = Math.min(18, Math.max(last, cur));
  const out: number[] = [];
  for (let w = cur; w <= last; w++) out.push(w);
  return out;
}

type Who = { player_id: string; name: string; pos: string | null; nfl_team: string | null };
function leaguePlayers(summary: J): Who[] {
  const seen = new Map<string, Who>();
  const add = (p: J) => {
    if (!p?.player_id || seen.has(String(p.player_id))) return;
    seen.set(String(p.player_id), { player_id: String(p.player_id), name: String(p.name ?? ""), pos: posOf(p), nfl_team: p.nfl_team ?? null });
  };
  for (const t of summary?.teams || []) for (const p of t.roster || []) add(p);
  for (const p of summary?.free_agents || []) add(p);
  return [...seen.values()];
}

export async function buildWeekly(summary: J, deps: WeeklyDeps) {
  const platform = String(summary?.platform || "");
  const season = num(summary?.season) ?? new Date().getUTCFullYear();
  const scoring = String(summary?.settings?.ddf?.scoring || "half_ppr");
  const col = pointsCol(scoring) as "points_std" | "points_half_ppr" | "points_ppr";
  const weeks = leagueWeeks(summary);
  const people = leaguePlayers(summary);
  // the league's own scoring rules (Yahoo statModifiers); without them every number is the source's default scoring
  const rules = leagueRules(summary);
  const missingStats = new Set<string>();
  const scored = (kind: "espn" | "sleeper" | "K" | "DEF", stats: Record<string, number> | null | undefined, fallback: number | null) => {
    if (!rules) return { points: fallback, rescored: false };
    const r = rescore(kind, stats, rules);
    if (!r) return { points: fallback, rescored: false };
    r.missing.forEach((m) => missingStats.add(`${kind === "espn" ? "ESPN" : kind === "sleeper" ? "Sleeper" : "ESPN " + kind}: ${m}`));
    return { points: r.points, rescored: true };
  };
  const unmatched: { player_id: string; name: string; reason: string }[] = [];

  // ---- identity ----
  const xw = await deps.xwalk();
  const bySleeper = new Map<string, XwalkRow>(), byEspn = new Map<string, XwalkRow>(), byYahoo = new Map<string, XwalkRow>();
  for (const r of xw) {
    if (r[0]) bySleeper.set(r[0], r);
    if (r[1]) byEspn.set(r[1], r);
    if (r[2]) byYahoo.set(r[2], r);
  }
  type Ids = { sleeper_id: string | null; espn_id: string | null; match: "id" | "team" | "team_name" | null };
  const ids = new Map<string, Ids>();
  for (const p of people) {
    if (p.pos === "K" || p.pos === "DEF") continue; // joined below against ESPN's K/DST list
    let r: XwalkRow | undefined;
    if (platform === "sleeper") r = bySleeper.get(p.player_id) ?? ([p.player_id, null, null, p.name, p.pos, p.nfl_team] as XwalkRow);
    else if (platform === "espn") r = byEspn.get(p.player_id) ?? ([null, p.player_id, null, p.name, p.pos, p.nfl_team] as XwalkRow);
    else { const y = yahooNum(p.player_id); r = y ? byYahoo.get(y) : undefined; }
    if (!r) { unmatched.push({ player_id: p.player_id, name: p.name, reason: "No Yahoo id in the Sleeper or Dynasty Daddy player lists" }); continue; }
    ids.set(p.player_id, { sleeper_id: r[0], espn_id: r[1], match: "id" });
  }
  const espnIds = [...new Set([...ids.values()].map((i) => i.espn_id).filter((x): x is string => !!x))];
  const sleeperIds = [...new Set([...ids.values()].map((i) => i.sleeper_id).filter((x): x is string => !!x))];

  // ---- data ----
  const [rows, games, kd] = await Promise.all([
    weeks.length ? deps.rows(season, weeks[0], espnIds, sleeperIds) : Promise.resolve([] as WarehouseRow[]),
    deps.schedule(season),
    people.some((p) => p.pos === "K" || p.pos === "DEF") ? deps.kdef(season).catch(() => null) : Promise.resolve(null),
  ]);
  const plays = new Map<number, Set<string>>();
  for (const g of games) {
    if (!plays.has(g.week)) plays.set(g.week, new Set());
    for (const t of [g.home_team, g.away_team]) { const c = teamCode(t); if (c) plays.get(g.week)!.add(c); }
  }
  const byes: Record<string, number[]> = {};
  const allTeams = new Set<string>(); for (const s of plays.values()) for (const t of s) allTeams.add(t);
  for (const t of allTeams) byes[t] = weeks.filter((w) => plays.has(w) && !plays.get(w)!.has(t));
  const isBye = (team: string | null, w: number) => { const c = teamCode(team); return !!c && plays.has(w) && !plays.get(w)!.has(c); };
  // kickoff per NFL team per week (nflverse gameday + gametime, US Eastern), for the live week: banked vs still to play
  const kickoffs: Record<string, Record<string, string>> = {};
  for (const g of games) {
    if (!weeks.includes(g.week) || !g.gameday || !g.gametime) continue;
    const at = etIso(String(g.gameday).slice(0, 10), String(g.gametime).slice(0, 5));
    for (const t of [g.home_team, g.away_team]) { const c = teamCode(t); if (c) (kickoffs[g.week] ||= {})[c] = at; }
  }

  const espnAt = new Map<string, WarehouseRow>(), sleeperAt = new Map<string, WarehouseRow>();
  const asOf: Record<string, string | null> = { espn: null, sleeper: null, schedule: games[0]?.as_of ?? null, kdef: kd?.as_of ?? null };
  for (const r of rows) {
    if (r.source === "espn") { espnAt.set(r.source_player_id + "|" + r.target_week, r); asOf.espn = r.as_of; }
    else if (r.sleeper_id) { sleeperAt.set(r.sleeper_id + "|" + r.target_week, r); asOf.sleeper = r.as_of; }
  }

  const kdefTeam = new Map<string, KdefRow[]>(), kdefById = new Map<string, KdefRow>();
  for (const k of kd?.players || []) kdefById.set(k.espn_id, k);
  for (const k of kd?.players || []) {
    const key = k.pos + "|" + teamCode(k.team);
    if (!kdefTeam.has(key)) kdefTeam.set(key, []);
    kdefTeam.get(key)!.push(k);
  }

  const players: Record<string, J> = {};
  for (const p of people) {
    const out: Record<string, Cell> = {};
    if (p.pos === "K" || p.pos === "DEF") {
      const list = kdefTeam.get(p.pos + "|" + teamCode(p.nfl_team)) || [];
      let k: KdefRow | undefined, match: string | null = null;
      if (p.pos === "K") { // a kicker: his ESPN id where the crosswalk has one, else his team's ESPN kicker of the same last name
        const r = platform === "espn" ? byEspn.get(p.player_id) ?? ([null, p.player_id] as unknown as XwalkRow) : platform === "sleeper" ? bySleeper.get(p.player_id) : byYahoo.get(yahooNum(p.player_id) ?? "");
        k = r?.[1] ? kdefById.get(r[1]) : undefined;
        if (k) match = "id";
        else { k = list.find((x) => lastName(x.name) === lastName(p.name)); if (k) match = "team_name"; }
      } else { k = list[0]; if (k) match = "team"; } // one D/ST per NFL team
      // a kicker ESPN files under another team (or none): the same full name at the same position
      if (!k && p.pos === "K") {
        const norm = (n: string) => n.toLowerCase().replace(/[^a-z]/g, "");
        k = (kd?.players || []).find((x) => x.pos === "K" && norm(x.name) === norm(p.name));
        if (k) match = "name";
      }
      const kNote = k && match === "name" ? `ESPN lists him ${k.team ? "with " + k.team : "without a team"}` : null;
      if (!kd) { unmatched.push({ player_id: p.player_id, name: p.name, reason: "ESPN's K/DEF projections could not be read just now" }); }
      else if (!k) { unmatched.push({ player_id: p.player_id, name: p.name, reason: `No ESPN ${p.pos === "K" ? "kicker" : "D/ST"} found for ${p.nfl_team ?? "an unknown team"}` }); }
      for (const w of weeks) {
        const bye = isBye(p.nfl_team, w);
        const v0 = k ? num(k.weeks[String(w)]) : null;
        const sc = k && v0 !== null ? scored(p.pos as "K" | "DEF", k.lines?.[String(w)], Math.round(v0 * 100) / 100) : { points: null, rescored: false };
        const v = sc.points;
        out[w] = bye ? { points: 0, source: k ? "espn_live" : null, bye, note: "BYE", rescored: !!rules }
          : v !== null ? { points: v, source: "espn_live", bye, note: kNote, rescored: sc.rescored }
          : { points: null, source: null, bye, note: k ? "ESPN gave no projection this week" : "Not matched to ESPN" };
      }
      players[p.player_id] = { name: p.name, pos: p.pos, nfl_team: p.nfl_team, sleeper_id: null, espn_id: k?.espn_id ?? null, match, weeks: out };
      continue;
    }
    const id = ids.get(p.player_id);
    for (const w of weeks) {
      const bye = isBye(p.nfl_team, w);
      const e = id?.espn_id ? espnAt.get(id.espn_id + "|" + w) : undefined;
      const s = id?.sleeper_id ? sleeperAt.get(id.sleeper_id + "|" + w) : undefined;
      const e0 = e ? num(e[col]) : null, s0 = s ? num(s[col]) : null;
      const es = e0 !== null ? scored("espn", e!.stats, e0) : null, ss = s0 !== null ? scored("sleeper", s!.stats, s0) : null;
      const ev = es ? es.points : null, sv = ss ? ss.points : null;
      if (bye) out[w] = { points: 0, source: ev !== null ? "espn" : sv !== null ? "sleeper" : null, bye, note: "BYE", rescored: !!rules };
      else if (ev !== null) out[w] = { points: ev, source: "espn", bye, note: null, rescored: es!.rescored };
      else if (sv !== null) out[w] = { points: sv, source: "sleeper", bye, note: null, rescored: ss!.rescored };
      else out[w] = { points: null, source: null, bye, note: !id ? "Not matched by id" : !SKILL.has(p.pos || "") ? `No weekly projection for ${p.pos}` : "No ESPN or Sleeper row this week" };
    }
    players[p.player_id] = { name: p.name, pos: p.pos, nfl_team: p.nfl_team, sleeper_id: id?.sleeper_id ?? null, espn_id: id?.espn_id ?? null, match: id?.match ?? null, weeks: out };
  }
  const scoring_basis = rules
    ? { rescored: true, text: "Every weekly number is the source's projected stat line rescored with your league's scoring settings.", missing: [...missingStats].sort(), notes: rulesNotes(rules) }
    : { rescored: false, text: `Your league's scoring settings are not in the league data, so these are each source's default ${scoring.replace("_", "-").toUpperCase()} scoring, not your league's.`, missing: [], notes: [] };
  return { shape: "ddf-league-weekly/0", season, scoring, scoring_basis, weeks, as_of: asOf, players, unmatched, byes, kickoffs };
}

// ---- live sources (fetched by the function, cached in platform_cache) ----

// Sleeper player DB + Dynasty Daddy, merged on sleeper_id: [sleeper, espn, yahoo, name, pos, team].
export async function fetchXwalk(f: Fetch): Promise<XwalkRow[]> {
  const sl = (await getJSON(f, "https://api.sleeper.app/v1/players/nfl", {}, "Sleeper")).body as Record<string, J> | null;
  const dd = await getJSON(f, "https://dynasty-daddy.com/api/v1/player/all/today", {}, "Dynasty Daddy").then((r) => r.body as J[] | null).catch(() => null);
  const m = new Map<string, XwalkRow>();
  for (const [sid, p] of Object.entries(sl || {})) {
    const pos = posOf(p);
    if (!pos || !(SKILL.has(pos) || pos === "K")) continue;
    const name = p.full_name || [p.first_name, p.last_name].filter(Boolean).join(" ");
    m.set(sid, [sid, p.espn_id ? String(p.espn_id) : null, p.yahoo_id ? String(p.yahoo_id) : null, String(name || ""), pos, p.team ?? null]);
  }
  for (const p of dd || []) {
    const sid = p?.sleeper_id ? String(p.sleeper_id) : null;
    const row: XwalkRow = sid && m.get(sid) ? m.get(sid)! : [sid, null, null, String(p?.full_name || ""), posOf(p), p?.team ?? null];
    if (!row[1] && p?.espn_id) row[1] = String(p.espn_id);
    if (!row[2] && p?.yahoo_id) row[2] = String(p.yahoo_id);
    if (sid) m.set(sid, row); else if (row[1] || row[2]) m.set("dd:" + (row[1] || row[2]), row);
  }
  return [...m.values()].filter((r) => r[1] || r[2] || r[0]);
}

// ESPN's weekly projections for every K and D/ST, all weeks in one read (statSourceId 1 = projection).
export async function fetchEspnKdef(f: Fetch, season: number, now: Date): Promise<{ as_of: string; players: KdefRow[] }> {
  const filter = { players: { filterSlotIds: { value: [17, 16] }, limit: 250, sortPercOwned: { sortPriority: 1, sortAsc: false } } };
  const url = `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${season}/segments/0/leaguedefaults/3?view=kona_player_info`;
  const got = await getJSON(f, url, { headers: { "x-fantasy-filter": JSON.stringify(filter), accept: "application/json" } }, "ESPN");
  const players: KdefRow[] = [];
  for (const e of (got.body as J)?.players || []) {
    const p = e.player || {};
    const pos = p.defaultPositionId === 5 ? "K" : p.defaultPositionId === 16 ? "DEF" : null;
    if (!pos) continue;
    const weeks: Record<string, number> = {}, lines: Record<string, Record<string, number>> = {};
    for (const s of p.stats || []) {
      if (s.statSourceId !== 1 || s.statSplitTypeId !== 1 || s.seasonId !== season || typeof s.appliedTotal !== "number") continue;
      weeks[String(s.scoringPeriodId)] = s.appliedTotal;
      if (s.stats && typeof s.stats === "object") lines[String(s.scoringPeriodId)] = s.stats; // the stat line, for league rescoring
    }
    players.push({ espn_id: String(p.id), name: String(p.fullName || ""), pos, team: PRO_TEAM[p.proTeamId] ?? null, weeks, lines });
  }
  if (!players.length) throw new Error("ESPN returned no kickers or defenses"); // never cache an empty read as a success
  return { as_of: now.toISOString(), players };
}

// "2026-11-27" + "16:30" US Eastern -> ISO UTC (EST or EDT, whichever reads back as that clock time)
export function etIso(day: string, time: string) {
  const fmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  for (const off of ["-05:00", "-04:00"]) {
    const d = new Date(`${day}T${time}:00${off}`);
    if (!isNaN(d.getTime()) && fmt.format(d) === time) return d.toISOString();
  }
  return new Date(`${day}T${time}:00-05:00`).toISOString();
}
