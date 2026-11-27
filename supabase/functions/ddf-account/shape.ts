// The stored league summary, "ddf-connected-league/0" (JEG-1732, staging only).
// One shape for Sleeper, Yahoo and ESPN. A value the platform did not give is null
// and gets a row in `missing` with the reason: never a zero or a default.

export const SUMMARY_VERSION = "ddf-connected-league/0";

export type Platform = "sleeper" | "yahoo" | "espn";

// The site's league settings, in app/next/sleeper-import.js settingsOf's shape.
export type DdfSettings = {
  scoring: "ppr" | "half_ppr" | "standard";
  superflex: boolean;
  superflexSlots?: number;
  roster?: { QB: number; RB: number; WR: number; TE: number; FLEX: number; BENCH: number; K: number; DST: number };
  teams?: number;
};

export type RosterPlayer = {
  player_id: string;
  name: string | null;
  position: string | null;
  nfl_team: string | null;
  slot: string | null; // starter slot, BN, IR, TAXI
  status: string | null; // injury designation as the platform gives it
};

export type TeamSummary = {
  team_key: string;
  name: string;
  managers: { id: string; name: string | null }[];
  standings: {
    wins: number | null;
    losses: number | null;
    ties: number | null;
    points_for: number | null;
    points_against: number | null;
    rank: number | null;
    rank_source: string | null;
  };
  faab_remaining: number | null;
  waiver_priority: number | null;
  roster: RosterPlayer[];
};

export type Matchup = {
  team_keys: string[];
  points: (number | null)[];
  projected_points: (number | null)[]; // team-level, platform's own; null where the platform has none
  is_playoffs: boolean;
};

export type LeagueSummary = {
  shape: typeof SUMMARY_VERSION;
  platform: Platform;
  league_key: string;
  season: number;
  name: string;
  pulled_at: string;
  current_week: number | null;
  settings: {
    num_teams: number | null;
    ddf: DdfSettings | null; // what DDF would use; the user confirms or edits it
    fit: Record<string, unknown> | null; // what the league has that DDF values cannot reflect
    roster_positions: string[];
    scoring_raw: unknown;
    playoff_start_week: number | null;
    playoff_teams: number | null;
    last_regular_week: number | null;
    trade_deadline: { week: number | null; date: string | null; none: boolean; source: string | null };
    waiver_type: string | null;
    faab_budget: number | null;
  };
  teams: TeamSummary[];
  my_team_key: string | null;
  schedule: { week: number; matchups: Matchup[] }[];
  probes?: Record<string, unknown>;
  missing: { path: string; reason: string }[];
  sources: string[];
};

export const SIZES = [8, 10, 12, 14];
// app/next/sleeper-import.js closestSize: between sizes rounds up, below 8 uses 8, above 14 uses 14 (Jeremy, 2026-11-24)
export function closestSize(n: number): number {
  for (const s of SIZES) if (s >= n) return s;
  return SIZES[SIZES.length - 1];
}

export function num(x: unknown): number | null {
  const n = typeof x === "string" && x.trim() !== "" ? Number(x) : x;
  return typeof n === "number" && isFinite(n) ? n : null;
}

export function int(x: unknown, lo = -Infinity, hi = Infinity): number | null {
  const n = num(x);
  return n !== null && Math.floor(n) === n && n >= lo && n <= hi ? n : null;
}

export class Missing {
  rows: { path: string; reason: string }[] = [];
  add(path: string, reason: string) {
    this.rows.push({ path, reason });
    return null;
  }
}

// Standings rank when the platform gives none: wins, then ties, then points for (labelled derived).
export function deriveRanks(teams: TeamSummary[], source: string) {
  if (teams.some((t) => t.standings.rank !== null)) return;
  if (teams.some((t) => t.standings.wins === null)) return;
  const order = [...teams].sort((a, b) =>
    (b.standings.wins! + 0.5 * (b.standings.ties ?? 0)) - (a.standings.wins! + 0.5 * (a.standings.ties ?? 0)) ||
    (b.standings.points_for ?? 0) - (a.standings.points_for ?? 0)
  );
  order.forEach((t, i) => {
    t.standings.rank = i + 1;
    t.standings.rank_source = source;
  });
}
