// Injury flag on a player (Jeremy, 2026-11-22: "It is a flag, not a stopper"). Display only: nothing here changes a
// value, a label, a rule, a count or an order. The connector's trade answers print it beside the player.
//
// Source: the site's daily Sleeper status copy, v2/player-status.js (window.TradeValueStatus, built from
// data/inputs/player_status.json by pipelines/build_v2_page.py; refreshed daily 13:10 UTC and Sunday 16:30 UTC).
// The rules are the site's, kept equal by tests/node/injury_flag_parity_check.mjs:
//   freshness and matching = app/v2/waivers.js statusFreshness / statusOf (dated, at most 6 days old, not future-dated;
//     same Sleeper id, NFL team and position);
//   severity = app/next/injury-flag.js severity (Out, IR, PUP, Suspended -> out; Doubtful; Questionable; else no flag).

export interface InjuryFlag { status: string; label: string; level: "out" | "doubtful" | "questionable"; body?: string }
export interface InjurySource { source: "Sleeper"; as_of: string | null; shown: boolean; note: string }
interface StatusRecord { team?: string; pos?: string; injury_status?: string | null; injury_body_part?: string | null }
export interface StatusCopy { as_of?: string | null; by_sleeper_id?: Record<string, StatusRecord> }

const MAX_AGE_MS = 6 * 24 * 60 * 60 * 1000;
const TEAM_ALIASES: Record<string, string> = { JAC: "JAX", LAR: "LA", WSH: "WAS", LVR: "LV" };
const team = (t: unknown) => { const c = String(t ?? "").trim().toUpperCase(); return TEAM_ALIASES[c] || c; };
const SEVERITY: Record<string, { label: string; level: InjuryFlag["level"] }> = {
  Out: { label: "Out", level: "out" }, IR: { label: "IR", level: "out" }, PUP: { label: "PUP", level: "out" },
  Sus: { label: "Suspended", level: "out" }, Doubtful: { label: "Doubtful", level: "doubtful" },
  Questionable: { label: "Questionable", level: "questionable" },
};
const ALIASES: Record<string, string> = { OUT: "Out", O: "Out", IR: "IR", "INJURED RESERVE": "IR", PUP: "PUP", SUS: "Sus",
  SUSP: "Sus", SUSPENDED: "Sus", DOUBTFUL: "Doubtful", D: "Doubtful", QUESTIONABLE: "Questionable", Q: "Questionable" };

export function severity(status: unknown): { status: string; label: string; level: InjuryFlag["level"] } | null {
  const name = typeof status === "string" ? ALIASES[status.trim().toUpperCase()] : undefined;
  return name ? { status: name, ...SEVERITY[name] } : null;
}

/** The status copy from the published player-status.js text, or null when it cannot be read. */
export function parseStatusScript(src: string | null): StatusCopy | null {
  if (!src) return null;
  const m = src.match(/window\.TradeValueStatus\s*=\s*([\s\S]*?);?\s*$/);
  if (!m) return null;
  try {
    const d = JSON.parse(m[1].trim().replace(/;$/, ""));
    return d && typeof d === "object" ? d : null;
  } catch {
    return null;
  }
}

/** Whether the copy may be shown at nowMs, and the line the answer carries about it. */
export function injurySource(copy: StatusCopy | null, nowMs: number): InjurySource {
  const at = copy && typeof copy.as_of === "string" ? Date.parse(copy.as_of) : NaN;
  if (!Number.isFinite(at)) return { source: "Sleeper", as_of: null, shown: false, note: "Injury status not shown: no dated Sleeper status copy." };
  const old = nowMs - at;
  if (at > nowMs || old > MAX_AGE_MS) {
    return { source: "Sleeper", as_of: copy!.as_of!, shown: false, note: `Injury status not shown: the Sleeper status copy is from ${copy!.as_of}, more than 6 days old.` };
  }
  return { source: "Sleeper", as_of: copy!.as_of!, shown: true, note: `Injury flags: Sleeper status as of ${copy!.as_of}. A flag, not a stopper: it changes no value or label.` };
}

/** One player's flag, or null (no status, a stale copy, or the id, team or position do not match). */
export function injuryOf(row: { sleeper_id?: unknown; team?: unknown; pos?: unknown } | null | undefined, copy: StatusCopy | null, source: InjurySource): InjuryFlag | null {
  if (!row || !source.shown || !copy?.by_sleeper_id || row.sleeper_id === null || row.sleeper_id === undefined) return null;
  const p = copy.by_sleeper_id[String(row.sleeper_id)];
  if (!p || !row.team || team(p.team) !== team(row.team) || p.pos !== row.pos) return null;
  // The Waivers rule shows these statuses only (app/v2/waivers.js statusOf).
  if (!["Questionable", "Doubtful", "Out", "IR", "PUP", "Sus"].includes(String(p.injury_status))) return null;
  const s = severity(p.injury_status);
  if (!s) return null;
  const body = typeof p.injury_body_part === "string" ? p.injury_body_part.replace(/\s+/g, " ").trim().slice(0, 40).toLowerCase() : "";
  return { status: s.status, label: s.label, level: s.level, ...(body ? { body } : {}) };
}
