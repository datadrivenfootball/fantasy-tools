// JEG-1012: tool logic for the remote MCP endpoint. Pure functions, no Deno
// APIs, so the same file runs under node in tests/test_mcp_remote.py.
//
// Lookups and trade math run here, so a tool call returns a small answer
// instead of the whole player list.

import { type Deps, finish, prepare, type Prepared } from "./state.ts";
import { type Finder, type FinderRow, findTradesForPair } from "./find-trades.ts";
import { closestNames, type NameMatch, matchName, notEvaluated, splitNames } from "./names.ts";
import { type BenchShareReadout, type FitContext, type FitFinder, type FitRow, type FitSides, benchWeightsFromReadout, buildFitContext, fitForTrade } from "./fit.ts";
import {
  type RosterShape,
  type ViabilityConfig,
  type ViabilityRow,
  type TradeOfferInput,
  type ScoredOffer,
  applyTrade,
  DEFAULT_CONFIG,
  pickStarters,
  runViabilityChecks,
  scoreAndRankOffers,
  selectPackage,
} from "./viability.ts";
import { kdefLine, LeagueInputError, MAX_TEAMS, MIN_TEAMS, nearestTeams, type LeagueRead, parseSlots, partnerIndex, readLeague, type Roster, shapeFromRoster, stateTeams } from "./league.ts";
import { askedWeek, type WeekFields, weekProp, withWeek } from "./week.ts";
import {
  type AnalysisDeps,
  type AnalysisResponse,
  COMPARE_SERIES,
  fmtNet,
  inspectionOf,
  type PageRow,
  pageRows,
  priorFor,
  SERIES_LABELS,
  slimDisagreement,
  slimMover,
} from "./analyses.ts";

export interface PlayerValue {
  player_key: number;
  name: string;
  pos: string;
  value: number;
  tier: string;
}

// JEG-1179: every answer carries the week it was priced on (WeekFields: week, default_week, weeks,
// missing_sources); sources_included lists the sources priced on that week.
export interface ValuesResponse extends WeekFields {
  attribution: string;
  as_of: string | null;
  setting: { scoring: string; teams: number; superflex: number };
  players: PlayerValue[];
  sources_included: string[];
  sources_excluded: Array<{ key: string; reason: string }>;
}

export type FetchValues = (
  scoring: string,
  teams: number,
  superflex: number,
  league?: Record<string, unknown>,
  week?: number | null,
) => Promise<ValuesResponse>;

/** Extended player record with per-chart values (from get-values?include=charts). */
export interface ChartPlayerValue extends PlayerValue {
  chart_values: Record<string, number | null>;
  /** Each chart's Indexed value: the market the other team judges by (JEG-1129). */
  chart_indexed?: Record<string, number | null>;
  ddf_value_charts: number | null;
  ddf_value_projections: number | null;
}

export interface ChartValuesResponse extends ValuesResponse {
  players: ChartPlayerValue[];
  /** The engine's bench-share readout, the fit rule's bench weights (JEG-1115). */
  bench_share?: BenchShareReadout;
}

/** Fetches values with chart series included (for find_trades). */
export type FetchValuesWithCharts = (
  scoring: string,
  teams: number,
  superflex: number,
  league?: Record<string, unknown>,
  week?: number | null,
) => Promise<ChartValuesResponse>;

export interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
}

const SCORINGS = ["standard", "half_ppr", "ppr"];
const POSITIONS = ["QB", "RB", "WR", "TE", "all"];
const EXPLAIN_TOPICS = [
  "methodology",
  "sources",
  "value_scale",
  "scoring_formats",
  "superflex",
  "tiers",
  "how_to_trade",
];

// JEG-1029: the series Risers & fallers offers (movers.js SERIES) and the sources Values auditing shows.
const MOVERS_SERIES = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "fantasycalc", "usatoday", "fantasypros", "cbs", "cbsros", "razzball", "espn"];
const AUDIT_SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn", "cbsros", "razzball"];

// Connector walkthrough 2026-11-21: scoring and superflex are required (or come from slots or a state) and never
// assumed; any team count from 4 to 20 is accepted and priced at the nearest of 8, 10, 12 or 14.
const settingsProps = {
  scoring: {
    type: "string",
    description: "Required unless a state is passed. League scoring: ppr, half_ppr, or standard (also PPR, 0.5ppr, half, non-ppr). Ask the user if unknown; never assume it.",
  },
  teams: {
    type: "integer",
    minimum: MIN_TEAMS,
    maximum: MAX_TEAMS,
    description: "Number of teams in the league (4 to 20; priced at the nearest of 8, 10, 12 or 14, and the answer says which).",
  },
  superflex: {
    type: "boolean",
    description: "Required unless a state or a superflex slot is given. Whether the league has a superflex slot (yes/no and 1/0 also accepted). Ask the user if unknown.",
  },
  slots: {
    type: ["object", "string", "array"],
    description: "Optional starting lineup and bench, in plain words: {QB:1, RB:2, WR:3, TE:1, FLEX:1, K:1, DEF:1, BN:5}, or the league's slot list as text (\"QB, RB, RB, WR, WR, WR, TE, W/R/T, K, DEF, BN, BN\"; Q/W/R/T or OP is superflex), or [QB, RB, WR, TE, FLEX, BENCH]. Kicker, defense and IR slots are read and left out. Saved in the state.",
  },
  state: {
    type: "string",
    description:
      "Optional: a DDF state from make_state or pasted from the site (a ```ddf-state block, JSON, or a site link). Supplies the league settings, slots and rosters it saved; explicit arguments win.",
  },
  ...weekProp,
};

// Connector walkthrough 2026-11-21: one paste for the whole league, or the teams as a list, plus which team is yours.
const leagueProps = {
  league_paste: {
    type: "string",
    description: "The whole league as copied from Yahoo, ESPN or Sleeper (or typed): each team's name on a line, then its players one per line (\"WR George Pickens\" and \"K Brandon McManus\" are fine). Read by the site's paste reader. Use with my_team.",
  },
  league_teams: {
    type: "array",
    maxItems: 20,
    description: "Every team in the league: [{name, players}], players as a list or one text of names (commas or new lines).",
    items: {
      type: "object",
      properties: {
        name: { type: "string" },
        players: { type: ["array", "string"], items: { type: "string" } },
      },
      required: ["name", "players"],
    },
  },
  my_team: { type: ["string", "integer"], description: "Which team is the user's: its name, or its 0-based index in the league." },
};

// JEG-1124: a one-letter name fits too many players to be useful; ask for a fuller name.
const MIN_NAME = 2;

const listProps = {
  give: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: what you give (Compare a trade)" },
  get: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: what you get (Compare a trade)" },
  mine: { type: "string", minLength: MIN_NAME, description: "Your roster: names separated by commas or new lines (not needed with a league and my_team)" },
  theirs: { type: "string", minLength: MIN_NAME, description: "Their roster: names separated by commas or new lines" },
  target: { type: "string", minLength: MIN_NAME, description: "One player name (Trade targets)" },
};

// Viability configuration properties, exposed as optional tool arguments.
const viabilityProps = {
  viable_only: {
    type: "boolean",
    default: true,
    description: "Default true: only trades that pass all 9 checks (the other team would likely accept). When none pass, the reply says so and shows the closest 1 or 2 with the check each fails. Set false for every candidate.",
  },
  roster_shape: {
    type: "object",
    description: "Starting lineup shape (default: QB 1, RB 2, WR 2, TE 1, FLEX 1, SUPERFLEX per league setting)",
    properties: {
      QB: { type: "integer", default: 1 }, RB: { type: "integer", default: 2 },
      WR: { type: "integer", default: 2 }, TE: { type: "integer", default: 1 },
      FLEX: { type: "integer", default: 1 }, SUPERFLEX: { type: "integer", default: 0 },
    },
  },
  min_ddf_edge: { type: "number", default: 0, description: "Minimum DDF value gain for viability (default 0)" },
  min_market_net: { type: "number", default: 0, description: "Minimum market-value gain for the other team (default 0)" },
  depth_player_cutoff: { type: "number", default: 0.5, description: "Minimum DDF value for a player to count as depth" },
  dead_weight_cutoff: { type: "number", default: 0.5, description: "Maximum DDF value for a droppable player" },
  min_rb_backups: { type: "integer", default: 1, description: "Minimum healthy RB backups beyond starters" },
  min_wr_backups: { type: "integer", default: 0, description: "Minimum healthy WR backups beyond starters" },
};

/** Build a RosterShape from tool args, defaulting SUPERFLEX from the league setting. */
function rosterShape(args: Record<string, unknown>, superflex: number, slots?: Record<string, number> | null): RosterShape {
  const rs = (args.roster_shape ?? shapeFromRoster(slots as Roster) ?? {}) as Record<string, unknown>;
  return {
    QB: Number(rs.QB ?? 1),
    RB: Number(rs.RB ?? 2),
    WR: Number(rs.WR ?? 2),
    TE: Number(rs.TE ?? 1),
    FLEX: Number(rs.FLEX ?? 1),
    SUPERFLEX: Number(rs.SUPERFLEX ?? (superflex ? 1 : 0)),
  };
}

/** Build a ViabilityConfig from tool args. */
function viabilityConfig(args: Record<string, unknown>): ViabilityConfig {
  return {
    ...DEFAULT_CONFIG,
    minDdfEdge: Number(args.min_ddf_edge ?? DEFAULT_CONFIG.minDdfEdge),
    minMarketNet: Number(args.min_market_net ?? DEFAULT_CONFIG.minMarketNet),
    depthPlayerCutoff: Number(args.depth_player_cutoff ?? DEFAULT_CONFIG.depthPlayerCutoff),
    deadWeightCutoff: Number(args.dead_weight_cutoff ?? DEFAULT_CONFIG.deadWeightCutoff),
    minRbBackups: Number(args.min_rb_backups ?? DEFAULT_CONFIG.minRbBackups),
    minWrBackups: Number(args.min_wr_backups ?? DEFAULT_CONFIG.minWrBackups),
  };
}

export const TOOLS = [
  {
    name: "get_values",
    description:
      "Current fantasy football trade values for the user's league settings, from Data Driven Football. DDF Value is the average of the four adjusted trade charts (value above waivers). Returns name, position, value and tier, best first. Values have no fixed maximum.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter by position" },
        limit: { type: "integer", minimum: 1, maximum: 200, default: 50, description: "Maximum players to return" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "get_player_value",
    description:
      "Look up one or more players by name and return their DDF Value and tier. Partial names work. A name that fits more than one player is reported as ambiguous instead of guessed. Typos and missing hyphens are matched when only one player is close.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        names: { type: "string", minLength: MIN_NAME, description: "Comma-separated player names" },
      },
      required: ["names"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "trade_targets",
    description:
      "Find players whose value is close to a given player's, as realistic 1-for-1 trade partners. Without player_name but with the league (league_paste or league_teams with my_team, or a state that saved them): finds the user's weakest starting slot against the league's typical starter there and lists players on other teams who would upgrade it, closest value first, with the team that has each.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        ...leagueProps,
        player_name: { type: "string", minLength: MIN_NAME, description: "Player to trade (or trade for). Leave out with a league for the user's weakest slot." },
        range_pct: { type: "number", minimum: 1, maximum: 50, default: 15, description: "How close in value, in percent" },
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter targets by position" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "compare_trade",
    description:
      "Compare a trade for the user: what they give against what they get, by the sum of DDF Values (a comma before Jr, Sr, II, III, IV or V stays with the name). The reply opens with one line: whether the user wins or loses and by how much. The verdict is a DDF Value sum: it is not lineup-aware. With the user's roster (mine, or a league with my_team, or a state that saved them) it adds how their starting lineup changes. Set by_source for the site's Compare a trade breakdown: the net for DDF Value and each published trade chart (rescaled), and how many charts agree.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        ...leagueProps,
        give: { type: "string", minLength: MIN_NAME, description: "Comma-separated names the user gives" },
        get: { type: "string", minLength: MIN_NAME, description: "Comma-separated names the user gets" },
        side_a: { type: "string", minLength: MIN_NAME, description: "Older name for give" },
        side_b: { type: "string", minLength: MIN_NAME, description: "Older name for get" },
        mine: { type: "string", minLength: MIN_NAME, description: "Optional: the user's roster, for the starting lineup change" },
        by_source: { type: "boolean", default: false, description: "One row per series, as the site's Compare a trade shows it (DDF Value and the four published charts)" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "read_state",
    description:
      "Read a DDF state pasted from the Data Driven Football site (a ```ddf-state block, JSON, or a site link): the league, rosters and trade the person was working on. Resolves names to players, prices them, and reports anything it could not match. Use this first when the user pastes site work.",
    inputSchema: {
      type: "object",
      properties: {
        state: { type: "string", description: "The pasted block, JSON or site link (a link's wk= picks the week)" },
        ...weekProp,
      },
      required: ["state"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "make_state",
    description:
      "Save the league from this chat as a Data Driven Football state: settings, slots, every team's roster (league_paste or league_teams, with my_team), and a trade or target player, by name. League settings plus a league and my_team is enough. Returns a site link and the same state as a block; pass the state to later calls instead of resending settings and rosters.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        ...leagueProps,
        ...listProps,
        view: { type: "string", enum: ["compare", "targets", "finder"], description: "Which site view to open; inferred if omitted" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "find_trades",
    description:
      "Find trade packages between two rosters, scored for viability. Lists trades where you gain DDF Value and at least 3 of 4 trade charts say the other team breaks even or wins. Each trade is scored on 9 viability checks (arbitrage, fairness, lineup improvement, position protection, depth, roster space, QB, guardrails) and labelled High/Med-High/Medium when viable. Each trade also carries the fit label the site's finder shows (Natural / Market supported / Force) with a one-line reason. By default only trades that pass every check are listed (viable_only true); when none pass, the closest 1 or 2 are shown with the check each fails. The reply opens with a one-line answer (also structuredContent.summary).",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        ...leagueProps,
        their_team: { type: ["string", "integer"], description: "With a league: the partner team's name or 0-based index" },
        mine: { type: "string", minLength: MIN_NAME, description: "Your full roster: names separated by commas or new lines (or give a league and my_team)" },
        theirs: { type: "string", minLength: MIN_NAME, description: "Their full roster: names separated by commas or new lines (or give a league and their_team)" },
        max_per_side: { type: "integer", minimum: 1, maximum: 4, default: 2, description: "Maximum players each side trades (default 2-for-2)" },
        min_rival_edge: { type: "number", minimum: 0, default: 0, description: "Minimum average chart-value edge the other team needs (0 = any fair trade)" },
        limit: { type: "integer", minimum: 1, maximum: 50, default: 10, description: "Maximum trade candidates to return" },
        ...viabilityProps,
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "find_trades_league",
    description:
      "Find the best trades across an entire league. Takes your roster and a list of opponents with their rosters, scores every candidate on 9 viability checks, and selects the best package of trades (no player sent twice, each opponent at most once). By default only trades that pass every check are listed (viable_only true); when none pass, the closest 1 or 2 are shown with the check each fails. Returns a short line per trade (players, your DDF Value gain, lineup change, label or failed checks in plain words, and the fit label Natural / Market supported / Force with its reason) and the package with your projected lineup after. The reply opens with a one-line answer (also structuredContent.summary).",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        ...leagueProps,
        mine: { type: "string", minLength: MIN_NAME, description: "Your full roster: names separated by commas or new lines (or give a league and my_team)" },
        opponents: {
          type: "array",
          description: "Opposing teams: [{name, roster}], roster as names separated by commas or new lines (or give a league and my_team)",
          items: {
            type: "object",
            properties: {
              name: { type: "string", description: "Team name" },
              roster: { type: "string", minLength: MIN_NAME, description: "Player names, separated by commas or new lines" },
            },
            required: ["name", "roster"],
          },
          minItems: 1,
          maxItems: 15,
        },
        max_per_side: { type: "integer", minimum: 1, maximum: 4, default: 2, description: "Maximum players each side trades" },
        min_rival_edge: { type: "number", minimum: 0, default: 0, description: "Minimum average chart-value edge the other team needs (0 = any fair trade)" },
        limit: { type: "integer", minimum: 1, maximum: 100, default: 10, description: "Maximum trade candidates to return" },
        ...viabilityProps,
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "risers_fallers",
    description:
      "Who gained and lost value since last week, as the site's Risers & fallers shows it: one series at a time (DDF Value by default), Week N-1 to the week served now, both priced for the user's league. Also lists where the market (DDF Value) and the projections (DDF Value (projections)) disagree: one moved 2.5 points or more while the other moved 1.0 or less. A big move or a drop to 0 carries a reason from the trade charts and projections. With the league (or a state that saved it) each player is marked yours, the team that has him, or free agent.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        ...leagueProps,
        series: { type: "string", enum: MOVERS_SERIES, default: "ddf_value", description: "Which series' change to show" },
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter by position" },
        limit: { type: "integer", minimum: 1, maximum: 25, default: 10, description: "Risers and fallers to show, each" },
        disagreements: { type: "boolean", default: true, description: "Also list where the market and the projections disagree" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "audit_values",
    description:
      "Audit the values for the user's league, as the site's Values auditing tab shows them. view health (default): the Health check's verdicts, each check pass or flag with the reason. view source: one source's build-up (published, indexed, adjusted) with its totals and its top players in its own order.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        view: { type: "string", enum: ["health", "source"], default: "health", description: "Health check or one source's build-up" },
        source: { type: "string", enum: AUDIT_SOURCES, default: "fantasycalc", description: "The source, for view source" },
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter the source view by position" },
        limit: { type: "integer", minimum: 1, maximum: 50, default: 15, description: "Players to show in the source view" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "explain",
    description:
      "Explain how Data Driven Football values work: methodology, sources, value scale, scoring formats, superflex, tiers, how to use values in trades.",
    inputSchema: {
      type: "object",
      properties: { topic: { type: "string", enum: EXPLAIN_TOPICS } },
      required: ["topic"],
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];

export class ToolInputError extends Error {}
// A dependency is down, not the caller's input: same message to the client, logged as an outage.
export class ToolUnavailableError extends ToolInputError {}

/** Extra dependencies for tools that need the finder (find_trades). */
export interface FinderDeps {
  finder: Finder | null;
  fetchCharts: FetchValuesWithCharts | null;
  /** JEG-1029: get-values' analysis blocks and the page modules that read them. */
  analysis?: AnalysisDeps;
}

const SCORING_ALIASES: Record<string, string> = {
  ppr: "ppr",
  fullppr: "ppr",
  full: "ppr",
  "1ppr": "ppr",
  "1.0ppr": "ppr",
  halfppr: "half_ppr",
  half: "half_ppr",
  "0.5ppr": "half_ppr",
  "0.5": "half_ppr",
  "05ppr": "half_ppr",
  point5ppr: "half_ppr",
  standard: "standard",
  std: "standard",
  nonppr: "standard",
  noppr: "standard",
  "0ppr": "standard",
};

function normalizeScoring(value: unknown): string {
  const key = String(value).trim().toLowerCase().replace(/[\s_-]+/g, "");
  const scoring = SCORING_ALIASES[key];
  if (!scoring) throw new ToolInputError(`invalid scoring: ${value}. Must be one of: ${SCORINGS.join(", ")} (also PPR, 0.5ppr, half, standard).`);
  return scoring;
}

const TRUE_WORDS = new Set(["1", "true", "yes", "y", "on"]);
const FALSE_WORDS = new Set(["0", "false", "no", "n", "off"]);

/** Missing uses the default. An unrecognised value is an error, not a silent false. */
function parseBool(value: unknown, name: string, fallback: boolean): boolean {
  if (value === undefined || value === null || value === "") return fallback;
  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;
  const word = String(value).trim().toLowerCase();
  if (TRUE_WORDS.has(word)) return true;
  if (FALSE_WORDS.has(word)) return false;
  throw new ToolInputError(`${name} must be true or false (got ${JSON.stringify(value)}).`);
}

function parseBounded(value: unknown, name: string, fallback: number, min: number, max: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const n = typeof value === "number" ? value : Number(String(value).trim());
  if (!Number.isInteger(n) || n < min || n > max) {
    throw new ToolInputError(`${name} must be an integer from ${min} to ${max}.`);
  }
  return n;
}

function parseNonNegative(value: unknown, name: string, fallback: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const n = typeof value === "number" ? value : Number(String(value).trim());
  if (!Number.isFinite(n) || n < 0) throw new ToolInputError(`${name} must be a number >= 0.`);
  return n;
}

/**
 * Connector walkthrough 2026-11-21 (Jeremy: "ask for them, never default silently"): scoring and superflex are
 * required, from the arguments, the slots (a superflex slot) or a pasted state; a missing one is an error that names
 * it. A team count from 4 to 20 is priced at the nearest supported count and says so; a missing count is priced as
 * 12 and says so.
 */
function settings(args: Record<string, unknown>) {
  let roster: Roster | null;
  try {
    roster = parseSlots(args.slots);
  } catch (e) {
    throw new ToolInputError((e as Error).message);
  }
  const missing: string[] = [];
  if (args.scoring === undefined || args.scoring === null || args.scoring === "") missing.push("scoring (ppr, half_ppr or standard)");
  const sfSlot = roster?.SUPERFLEX !== undefined ? roster.SUPERFLEX > 0 : undefined;
  if ((args.superflex === undefined || args.superflex === null || args.superflex === "") && sfSlot === undefined) {
    missing.push("superflex (yes or no)");
  }
  if (missing.length) {
    throw new ToolInputError(
      `Missing league settings: ${missing.join(" and ")}. Ask the user for ${missing.length === 1 ? "it" : "them"}; they are never assumed. ` +
        "Or pass a state from make_state, which saves them.",
    );
  }
  const scoring = normalizeScoring(args.scoring);
  const notes: string[] = [];
  let teams = 12;
  if (args.teams === undefined || args.teams === null || args.teams === "") {
    notes.push("Team count not given: priced as 12 teams.");
  } else {
    const asked = Number(args.teams);
    if (!Number.isInteger(asked) || asked < MIN_TEAMS || asked > MAX_TEAMS) {
      throw new ToolInputError(`invalid teams: ${args.teams}. Give the league's team count, a whole number from ${MIN_TEAMS} to ${MAX_TEAMS}.`);
    }
    teams = nearestTeams(asked);
    if (teams !== asked) notes.push(`Priced as a ${teams}-team league, the nearest size the values support to your ${asked} teams.`);
  }
  const superflex = (args.superflex === undefined || args.superflex === null || args.superflex === ""
    ? sfSlot!
    : parseBool(args.superflex, "superflex", false))
    ? 1
    : 0;
  // JEG-1031: the rest of a pasted league (roster shape, shares, weeks, advanced), priced by get-values.
  let league = args.league && typeof args.league === "object" ? args.league as Record<string, unknown> : undefined;
  const slots = roster ? Object.fromEntries(Object.entries(roster).filter(([k]) => k !== "SUPERFLEX")) : {};
  if (Object.keys(slots).length) {
    league = { ...(league ?? {}), roster: { ...((league?.roster as Record<string, unknown>) ?? {}), ...slots } };
  }
  const savedRoster = roster ? { ...slots, SUPERFLEX: superflex } : null;
  // The finders' lineup shape: this call's slots, else the saved league's roster (a state's league.roster).
  const savedShape = (league?.roster ?? null) as Record<string, number> | null;
  const lineup = savedRoster ?? (savedShape ? { ...savedShape, SUPERFLEX: superflex } : null);
  return { scoring, teams, superflex, league, roster: savedRoster, lineup, notes };
}

function position(args: Record<string, unknown>): string {
  const pos = String(args.position ?? "all");
  if (!POSITIONS.includes(pos)) {
    throw new ToolInputError(`invalid position: ${pos}. Must be one of: ${POSITIONS.join(", ")}`);
  }
  return pos;
}

function header(data: ValuesResponse, s: { scoring: string; teams: number; superflex: number; league?: Record<string, unknown> }): string[] {
  const bits = [s.scoring, `${s.teams} teams`];
  if (s.superflex) bits.push("superflex");
  const league = s.league;
  const roster = league?.roster && typeof league.roster === "object" ? league.roster as Record<string, unknown> : null;
  if (roster) {
    const slots = ["QB", "RB", "WR", "TE", "FLEX", "BENCH"].filter((k) => roster[k] !== undefined);
    if (slots.length) bits.push(`roster ${slots.map((k) => `${k}${roster[k]}`).join(" ")}`);
  }
  const shares = league?.shares && typeof league.shares === "object" ? league.shares as Record<string, unknown> : null;
  if (shares) {
    const parts = ["QB", "RB", "WR", "TE"].filter((k) => shares[k] !== undefined)
      .map((k) => `${k} ${Number(shares[k]).toFixed(2)}`);
    if (parts.length) bits.push(`shares ${parts.join(" ")}`);
  }
  return [
    data.attribution,
    `As of: ${data.as_of || "unknown"}`,
    `Settings: ${bits.join(", ")}`,
  ];
}

// Exact or unique partial match, else a single close typo. Ambiguous queries return null
// (the caller reads matchName for the warning). Kept for callers that only need the player.
export function findPlayer(players: PlayerValue[], query: string): PlayerValue | null {
  const byKey = savedKey(query);
  if (byKey) return players.find((p) => String(p.player_key) === byKey) ?? null;
  const hit = matchName(players, query);
  return hit.match === "ambiguous" ? null : hit.player;
}

/** A player a state saved by key is passed as "#key" (state.ts prepare); null for a typed name. */
function savedKey(input: string): string | null {
  return /^#(\d{1,9})$/.exec(String(input).trim())?.[1] ?? null;
}

/** The league for a roster tool (league_paste, league_teams or a state's teams), or null when none was given. */
function leagueOf(a: Record<string, unknown>, rows: PlayerValue[], deps?: Deps): LeagueRead | null {
  try {
    return readLeague(a, rows, deps?.paste ?? null);
  } catch (e) {
    if (e instanceof LeagueInputError) throw new ToolInputError(e.message);
    throw e;
  }
}

function partnerOf(league: LeagueRead, raw: unknown): number {
  try {
    return partnerIndex(league, raw);
  } catch (e) {
    if (e instanceof LeagueInputError) throw new ToolInputError(e.message);
    throw e;
  }
}

const hasLeagueInput = (a: Record<string, unknown>) =>
  (typeof a.league_paste === "string" && a.league_paste.trim() !== "") || Array.isArray(a.league_teams) ||
  (a.my_team !== undefined && a.my_team !== null && a.my_team !== "");

/** The user's team in a league, or an error that lists the teams. */
function myTeamOf(league: LeagueRead): number {
  if (league.mine !== null) return league.mine;
  throw new ToolInputError(`my_team is required with a league: which team is the user's? Teams: ${league.teams.map((t, i) => `${i} ${t.name}`).join(", ")}.`);
}

/** A state entry for a roster name: the player's key when the name (or a saved #key) is one player. */
function workEntry(players: PlayerValue[], input: string, key?: string | null): { key?: string; name: string } {
  if (key) return { key, name: input };
  const p = findPlayer(players, input);
  return p ? { key: String(p.player_key), name: p.name } : { name: input };
}

/** Every league team, saved in the state so later calls need only the state. */
function leagueWork(league: LeagueRead | null, players: PlayerValue[]): Record<string, unknown> {
  if (!league) return {};
  return {
    teams: stateTeams(league, (n, k) => workEntry(players, n, k)),
    ...(league.mine !== null ? { my_team: league.mine } : {}),
  };
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

interface SlimPlayer { name: string; pos: string; value: number | null }

function slimOffer(o: {
  team: string;
  userGives: Array<{ name: string; pos: string; ddfValue: number | null }>;
  userGets: Array<{ name: string; pos: string; ddfValue: number | null }>;
  ddfEdge: number;
  userLineupDelta: number;
  viable: boolean;
  label: string | null;
  temporaryGap: boolean;
  checks: Array<{ name: string; passed: boolean }>;
  fit?: string | null;
  fitReason?: string | null;
  fitSides?: FitSides | null;
}, withTeam: boolean) {
  const side = (rows: Array<{ name: string; pos: string; ddfValue: number | null }>): SlimPlayer[] =>
    rows.map((p) => ({ name: p.name, pos: p.pos, value: p.ddfValue }));
  const failed = o.checks.filter((c) => !c.passed).map((c) => c.name);
  return {
    ...(withTeam ? { team: o.team } : {}),
    userGives: side(o.userGives),
    userGets: side(o.userGets),
    ddfEdge: round1(o.ddfEdge),
    lineup: round1(o.userLineupDelta),
    viable: o.viable,
    label: o.label,
    failed,
    ...(o.temporaryGap ? { temporaryGap: true } : {}),
    // JEG-1115: the fit label the finder shows (Natural / Market supported / Force) and its reason.
    ...(o.fit ? { fit: o.fit, fitReason: o.fitReason ?? null } : {}),
    // JEG-1329: the other team's side of the same tradeFit call (their Trade chart average net and
    // starters change) and roster construction for both teams. Your side's numbers are ddfEdge,
    // lineup and the fit reason; the construction issues are in the fit reason too.
    ...(o.fit && o.fitSides ? {
      theirs: { marketNet: round1(o.fitSides.theirs.net), starters: round1(o.fitSides.theirs.starters),
        constructionOk: o.fitSides.theirs.construction.ok },
      yours: { constructionOk: o.fitSides.yours.construction.ok },
    } : {}),
  };
}

// Connector walkthrough 2026-11-21 (part B): the viability checks in plain words, for the text (structuredContent
// keeps the check names). Each reads as the reason a trade fails.
const CHECK_WORDS: Record<string, string> = {
  arbitrage: "you don't gain DDF Value",
  perceived_fairness: "they'd see it as unfair",
  user_lineup_improves: "your starting lineup doesn't improve",
  their_lineup_improves: "their starting lineup doesn't improve",
  position_protection: "it leaves their starting lineup weaker or a slot empty",
  depth: "it leaves a team too thin at RB or WR",
  roster_space: "a team has no one to drop for the extra player",
  qb_kept: "a team is left with no QB",
  user_guardrails: "it breaks one of your guardrails",
};
const plainCheck = (name: string) => CHECK_WORDS[name] ?? name.replace(/_/g, " ");
// app/v2/finder.js FIT_TIPS.force, said once per reply where a Force fit first shows.
const FORCE_MEANING = "(Force fit: a roster would be broken, a side loses, or the other team does not clear the bar on the trade charts.)";
const signed = (n: number) => (n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1));

function tradeLine(index: number, o: ReturnType<typeof slimOffer>, team?: string): string {
  const side = (rows: SlimPlayer[]) => rows.map((p) => `${p.name} (${p.pos} ${p.value ?? "?"})`).join(" + ");
  const tag = o.viable ? (o.label ?? "likely accepted") : `fails: ${o.failed.map(plainCheck).join("; ") || "a check"}`;
  const vs = team ? ` with ${team}:` : "";
  // JEG-1329: their starters change on the Trade chart average (their net is in the fit reason).
  const theirs = o.theirs ? ` | their starters ${signed(o.theirs.starters)}` : "";
  const line = `${index + 1}.${vs} give ${side(o.userGives)} → get ${side(o.userGets)} | your gain ${signed(o.ddfEdge)} | your lineup ${signed(o.lineup)}${theirs} | ${tag}`;
  // JEG-1115: the finder's fit label and one-line reason (fitText opens with the label).
  return o.fit ? `${line}${o.fitReason ? `\n   ${o.fitReason}` : ` | ${o.fit}`}` : line;
}

// JEG-1123: the text lists the top rows only, so a long result is not sent twice;
// structuredContent carries every row once and the site link opens the full list.
const TEXT_ROWS = 5;

function tradeLines<T extends ReturnType<typeof slimOffer>>(rows: T[], team?: (o: T) => string, said = { force: false }): string[] {
  const lines: string[] = [];
  rows.slice(0, TEXT_ROWS).forEach((o, i) => {
    lines.push(tradeLine(i, o, team?.(o)));
    if (o.fit === "Force" && !said.force) {
      said.force = true;
      lines.push(`   ${FORCE_MEANING}`);
    }
  });
  const more = rows.length - TEXT_ROWS;
  if (more > 0) lines.push(`${more} more in the structured result and on the site (link below).`);
  return lines;
}

/** "give A + B to Team 10 for C (+9.5 for you)": one trade in a sentence. */
function tradePhrase(o: { userGives: SlimPlayer[]; userGets: SlimPlayer[]; ddfEdge: number }, team?: string): string {
  const names = (rows: SlimPlayer[]) => rows.map((p) => p.name).join(" + ");
  return `give ${names(o.userGives)}${team ? ` to ${team}` : ""} for ${names(o.userGets)} (${signed(o.ddfEdge)} for you)`;
}

/** The plain reasons a closest (non-viable) trade fails, each with the check's own detail. */
function failReasons(o: ScoredOffer): string[] {
  return o.checks.filter((c) => !c.passed).map((c) => `${plainCheck(c.name)} (${c.detail.charAt(0).toLowerCase()}${c.detail.slice(1)})`);
}

/**
 * Decision 4A (Jeremy, 2026-11-21: "Viable trades only, with a closest fallback when none"): the finders' one-line
 * answer. `who` names the other side ("the other team", or the partner's name).
 */
function tradeSummary(
  shown: Array<ReturnType<typeof slimOffer> & { team?: string }>,
  closest: Array<ReturnType<typeof slimOffer> & { team?: string }>,
  viableCount: number,
  total: number,
  viableOnly: boolean,
  who: string,
): string {
  const best = shown[0];
  if (viableOnly && viableCount && best) {
    return `${viableCount} trade${viableCount === 1 ? "" : "s"} ${who} would likely accept; best: ${tradePhrase(best, best.team)}.`;
  }
  if (closest.length) {
    const c = closest[0];
    const why = c.failed.map(plainCheck);
    return `No trade passes every check; the closest is ${tradePhrase(c, c.team)}, which fails ${why.length === 1 ? "one" : why.length}: ${why.join("; ")}.`;
  }
  if (!viableOnly && best) {
    return `${total} trade${total === 1 ? "" : "s"} found, ${viableCount} ${who} would likely accept; first: ${tradePhrase(best, best.team)}.`;
  }
  return "No trade found where you gain DDF Value and the trade charts say the other team breaks even or wins.";
}

// JEG-1115: fit reasons must fit inside the existing JEG-1123 reply budgets. Limits are
// upper bounds (Jeremy, Oct 26); keep a ranked prefix and the entire selected package.
const bytes = (result: ToolResult) => new TextEncoder().encode(JSON.stringify(result)).length;
// JEG-1329 (pick B, 2026-10-29): the site link does not count against the reply budget. It opens the
// full list on the site, and a league link grows with every team it carries, so counting it would cost
// trade rows. Measured as the reply with the link left out of the text and site_url.
// Connector walkthrough 2026-11-21: the saved state is left out the same way. It carries every league roster (by key)
// so a later call needs only the state, and it grows with each team as the link does.
const budgetBytes = (result: ToolResult) => {
  const url = result.structuredContent?.site_url;
  const sc = result.structuredContent;
  const content = typeof url === "string" && url
    ? result.content.map((c) => ({ ...c, text: c.text.split(url).join("") }))
    : result.content;
  return bytes({ ...result, content, ...(sc ? { structuredContent: { ...sc, site_url: "", state: null } } : {}) });
};
const tradeBudget = (name: string, limit: number) => name === "find_trades"
  ? (limit <= 10 ? 6700 : 17000) : (limit <= 10 ? 8000 : 11500);
const SIZE_ERROR = "This trade reply is too large to show with complete fit reasons. Try fewer opponents or shorter roster/team names.";

function boundedTrades<T>(rows: T[], name: string, limit: number,
  render: (shown: T[], shortened: boolean) => ToolResult): ToolResult {
  // Leave room for #1024's week metadata/text. rpc.ts checks the exact final result after
  // every decorator, so an oversized envelope is an honest error, never a silent overflow.
  const budget = tradeBudget(name, limit) - 512;
  for (let count = rows.length; count >= Math.min(1, rows.length); count--) {
    const result = render(rows.slice(0, count), count < rows.length);
    if (budgetBytes(result) < budget) return result;
  }
  throw new ToolInputError(SIZE_ERROR);
}

/** Final wire guard, after state links and optional week metadata have been attached. */
export function checkTradeReplySize(name: string, result: ToolResult): void {
  if ((name === "find_trades" || name === "find_trades_league") && !result.isError &&
    budgetBytes(result) >= tradeBudget(name, Number(result.structuredContent?.limit) || 10)) {
    throw new ToolInputError(SIZE_ERROR);
  }
}

function foundLine(total: number, shown: number, limit: number, viableOnly: boolean): string {
  const noun = total === 1 ? "trade" : "trades";
  const which = viableOnly ? " viable" : "";
  if (shown === limit || total <= shown) return `Found ${total} ${noun} (showing ${shown}${which}).`;
  return `Found ${total} ${noun} (showing ${shown}${which} of limit ${limit}).`;
}

interface ResolvedNames<T extends PlayerValue> {
  matched: T[];
  unmatched: string[];
  ambiguous: Array<{ input: string; suggestions: string[] }>;
  notes: string[];
  /** Connector walkthrough 2026-11-21: kickers and defenses left out, counted (folded into one line, not one per name). */
  kickers: number;
  defenses: number;
  /** The kicker and defense names as given, named in the folded line when there are only a few. */
  kdefNames: string[];
  /** The closest names matchName offered for each unmatched name (no extra scan). */
  closest: Record<string, string[]>;
}

/** JEG-1124: one trimmed name, rejected when it is too short to pick out one player. */
function checkName(name: string, field: string): string {
  if (name.length < MIN_NAME) {
    throw new ToolInputError(
      `${field}: name too short (${JSON.stringify(name)}). Use a fuller player name, at least ${MIN_NAME} characters.`,
    );
  }
  return name;
}

/** A comma-separated name list, each name checked by checkName. */
function playerNames(raw: unknown, field: string): string[] {
  return splitNames(raw).map((n) => checkName(n, field));
}

function resolveNames<T extends PlayerValue>(players: T[], names: string[]): ResolvedNames<T> {
  const matched: T[] = [];
  const seen = new Set<number>();
  const unmatched: string[] = [];
  const ambiguous: Array<{ input: string; suggestions: string[] }> = [];
  const notes: string[] = [];
  const closest: Record<string, string[]> = {};
  let kickers = 0;
  let defenses = 0;
  const kdefNames: string[] = [];
  for (const input of names) {
    const saved = savedKey(input);
    if (saved) {
      const p = players.find((row) => String(row.player_key) === saved);
      if (!p) { notes.push(`A saved player (key ${saved}) is not priced this week; left out.`); continue; }
      if (!seen.has(p.player_key)) { seen.add(p.player_key); matched.push(p); }
      continue;
    }
    // A kicker or defense is not valued: left out with a note, never matched to another player and never a stop.
    const kd = notEvaluated(input, players);
    if (kd) {
      if (kd.pos === "K") kickers++;
      else defenses++;
      kdefNames.push(input);
      continue;
    }
    const hit: NameMatch<T> = matchName(players, input);
    if (hit.match === "ambiguous") {
      ambiguous.push({ input, suggestions: hit.suggestions.map((p) => p.name) });
      notes.push(hit.note);
      continue;
    }
    if (!hit.player) {
      // A kicker or defense matchName knows by name (the site's kicker list) is counted, never "not found".
      const kdNote = /: (kicker|defense), not valued$/.exec(hit.note);
      if (kdNote) {
        if (kdNote[1] === "kicker") kickers++;
        else defenses++;
        kdefNames.push(input);
        continue;
      }
      unmatched.push(input);
      notes.push(hit.note || `${input}: NOT FOUND`);
      if (hit.suggestions.length) closest[input] = hit.suggestions.map((p) => p.name);
      continue;
    }
    if (seen.has(hit.player.player_key)) {
      notes.push(`${hit.player.name} listed more than once; counted once.`);
      continue;
    }
    seen.add(hit.player.player_key);
    matched.push(hit.player);
    if (hit.note) notes.push(hit.note);
  }
  return { matched, unmatched, ambiguous, notes, kickers, defenses, kdefNames, closest };
}

/**
 * Connector walkthrough 2026-11-21 (part B): the name notices of one or more rosters, folded into a few lines that
 * follow the answer: "Left out: 12 kickers and 12 defenses (not valued).", one "Not found: ..." line, one "Could be
 * more than one player: ..." line, and one "Read as: ..." line for typo and partial matches. `team` labels an
 * opponent's names. The league paste's own counts and unsure lines come in through `league`.
 */
function nameLines(
  sources: Array<{ res: ResolvedNames<PlayerValue>; team?: string }>,
  league?: LeagueRead | null,
): string[] {
  let kickers = league?.kickers ?? 0;
  let defenses = league?.defenses ?? 0;
  const kdefNames: string[] = [];
  const notFound: string[] = [];
  const unsure: string[] = [...(league?.unsure ?? [])];
  const readAs: string[] = [];
  const other: string[] = [];
  for (const { res, team } of sources) {
    kickers += res.kickers;
    defenses += res.defenses;
    kdefNames.push(...res.kdefNames.map((n) => (team ? `${n} (${team})` : n)));
    const where = (input: string, extra = "") => `${input}${team || extra ? ` (${[team, extra].filter(Boolean).join("; ")})` : ""}`;
    for (const input of res.unmatched) {
      const near = res.closest[input];
      notFound.push(where(input, near?.length ? `closest: ${near.join(", ")}` : ""));
    }
    for (const a of res.ambiguous) unsure.push(`${where(a.input)} could be ${a.suggestions.join(" or ")}`);
    for (const note of res.notes) {
      if (/: NOT FOUND|: AMBIGUOUS/.test(note)) continue;
      const tagged = team ? `${note} (${team})` : note;
      if (/^(matched|interpreted) "|is listed as/.test(note)) readAs.push(tagged);
      else other.push(tagged);
    }
  }
  const lines: string[] = [];
  const kd = kdefLine(kickers, defenses);
  // A few are named (a trade's kicker); a league's dozens are only counted.
  if (kd) lines.push(kickers + defenses <= 3 && kdefNames.length === kickers + defenses ? `${kd.slice(0, -1)}: ${kdefNames.join(", ")}.` : kd);
  if (notFound.length) lines.push(`Not found: ${notFound.join(", ")}.`);
  if (unsure.length) lines.push(`Could be more than one player: ${unsure.join("; ")}.`);
  if (readAs.length) lines.push(`Read as: ${readAs.join("; ")}.`);
  return lines.concat(other);
}

/** "2 not found" plus, when any, "1 fits more than one player (left out; ask which)". */
function missed<T extends PlayerValue>(res: ResolvedNames<T>): string {
  const parts = [`${res.unmatched.length} not found`];
  if (res.ambiguous.length) parts.push(`${res.ambiguous.length} fit${res.ambiguous.length === 1 ? "s" : ""} more than one player (left out; ask which)`);
  return parts.join(", ");
}

/** Only set when a roster had an ambiguous name, so the usual reply stays the same size. */
function ambiguousOf<T extends PlayerValue>(res: ResolvedNames<T>): { ambiguous?: Array<{ input: string; suggestions: string[] }> } {
  return res.ambiguous.length ? { ambiguous: res.ambiguous } : {};
}

/**
 * JEG-1124: a name that fits several players, or (Jeremy 2026-10-30, "Letter A.") matches no
 * player, stops a compare so the model asks which one. A not-found name lists its closest names.
 */
function stopOnUnresolved<T extends PlayerValue>(players: T[], ...sides: Array<ResolvedNames<T>>): void {
  const hits = sides.flatMap((side) => side.ambiguous);
  const missing = sides.flatMap((side) => side.unmatched);
  if (!hits.length && !missing.length) return;
  const parts: string[] = [];
  if (hits.length) {
    const each = hits.map((h) => `"${h.input}" could be ${h.suggestions.join(", ")}`);
    parts.push(`More than one player fits: ${each.join("; ")}.`);
  }
  if (missing.length) {
    const each = missing.map((input) => {
      const near = closestNames(players, input, matchName(players, input)).map((p) => p.name);
      return `"${input}" matches no player${near.length ? `; closest: ${near.join(", ")}` : ""}`;
    });
    parts.push(`${each.join(". ")}.`);
  }
  throw new ToolInputError(`${parts.join(" ")} Ask the user which player they meant, then call again with the full name.`);
}

function emptyRoster<T extends PlayerValue>(side: string, res: ResolvedNames<T>): string {
  const why = [kdefLine(res.kickers, res.defenses), ...res.notes].filter(Boolean);
  if (why.length) return `No players matched on ${side}. ${why.join(" ")}`;
  return `No players matched on ${side}. Check the spelling.`;
}

function parseOpponents(raw: unknown): Array<{ name: string; roster: string }> {
  if (typeof raw === "string") {
    throw new ToolInputError("opponents must be an array of {name, roster}, not a string.");
  }
  if (!Array.isArray(raw) || !raw.length) throw new ToolInputError("opponents is required: an array of {name, roster}.");
  if (raw.length > 15) throw new ToolInputError("too many opponents (max 15)");
  return raw.map((opp, i) => {
    if (!opp || typeof opp !== "object" || Array.isArray(opp)) {
      throw new ToolInputError(`opponents[${i}] must be an object with name and roster.`);
    }
    const row = opp as Record<string, unknown>;
    const name = String(row.name ?? "").trim();
    if (!name) throw new ToolInputError(`opponents[${i}].name is required.`);
    if (typeof row.roster !== "string") {
      throw new ToolInputError(`opponents[${i}].roster must be a comma-separated string of names.`);
    }
    playerNames(row.roster, `opponents[${i}].roster`);
    return { name, roster: row.roster };
  });
}

function ok(text: string, structured: Record<string, unknown>): ToolResult {
  return { content: [{ type: "text", text }], structuredContent: structured };
}

// JEG-1179: every tool prices the week get-values picks (the site's default) or the week asked for
// (`week`, or `wk=` in a pasted site link). The fetchers carry it; the result gets the week fields.
export async function runTool(
  name: string,
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  const week = askedWeek(args);
  if (Number.isNaN(week)) {
    throw new ToolInputError(`invalid week: ${args.week}. Give a whole number from 1 to 22, or leave it out for the default week.`);
  }
  let priced: ValuesResponse | null = null;
  const weekValues: FetchValues = async (scoring, teams, superflex, league) =>
    (priced = await fetchValues(scoring, teams, superflex, league, week));
  const charts = finderDeps?.fetchCharts;
  const analysis = finderDeps?.analysis?.fetchAnalysis;
  const weekDeps: FinderDeps | undefined = finderDeps && {
    ...finderDeps,
    fetchCharts: charts
      ? async (scoring, teams, superflex, league) => (priced = await charts(scoring, teams, superflex, league, week))
      : null,
    ...(finderDeps.analysis ? {
      analysis: {
        ...finderDeps.analysis,
        fetchAnalysis: analysis
          ? async (scoring, teams, superflex, league, _week, includes) =>
            (priced = await analysis(scoring, teams, superflex, league, week, includes))
          : null,
      },
    } : {}),
  };
  const result = await runPricedTool(name, args, weekValues, deps, weekDeps);
  return withWeek(result, priced, week);
}

async function runPricedTool(
  name: string,
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  if (name === "read_state") return await readState(args, fetchValues, deps);
  if (name === "make_state") return await makeState(args, fetchValues, deps);
  if (name === "find_trades") return await findTradesHandler(args, fetchValues, deps, finderDeps);
  if (name === "find_trades_league") return await findTradesLeagueHandler(args, fetchValues, deps, finderDeps);
  if (name === "risers_fallers") return await risersFallersHandler(args, deps, finderDeps?.analysis);
  if (name === "audit_values") return await auditValuesHandler(args, deps, finderDeps?.analysis);
  const prepared = prepare(args, deps);
  args = prepared.args;
  if (name === "explain") {
    const dummy = { scoring: "ppr", teams: 12, superflex: 0 };
    const out = explain(String(args.topic ?? ""));
    const first = String(out.structuredContent?.text ?? "").match(/^.*?[.!?](?=\s|$)/)?.[0] ?? "";
    return finish(out, { prepared, deps, settings: dummy, view: "targets", bare: true, summary: first });
  }

  const s = settings(args);
  const entry = (input: string, p: PlayerValue | null) => p ? { key: String(p.player_key), name: p.name } : { name: input };

  if (name === "get_values") {
    const pos = position(args);
    const limit = parseBounded(args.limit, "limit", 50, 1, 200);
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const players = data.players.filter((p) => pos === "all" || p.pos === pos).slice(0, limit)
      .map((p) => ({ name: p.name, pos: p.pos, value: p.value, tier: p.tier }));
    const text = [
      ...header(data, s),
      `Sources included: ${data.sources_included.join(", ")}`,
      `${players.length} players, best first.`,
      ...players.map((p) => `${p.name} | ${p.pos} | ${p.value} | ${p.tier}`),
    ].join("\n");
    const label = pos === "all" ? "players" : `${pos}s`;
    const summary = players.length
      ? `Top ${label} by DDF Value: ${players.slice(0, 3).map((p) => `${p.name} ${p.value}`).join(", ")} (${players.length} shown).`
      : `No ${label} are priced for these settings.`;
    return finish(
      ok(text, { as_of: data.as_of, setting: data.setting, sources_included: data.sources_included, players }),
      { prepared, deps, settings: s, view: "targets", summary },
    );
  }

  if (name === "get_player_value") {
    const names = playerNames(args.names, "names");
    if (!names.length) throw new ToolInputError("names is required");
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const results = names.map((input) => {
      const hit = matchName(data.players, input);
      return { input, player: hit.match === "ambiguous" ? null : hit.player, match: hit.match, suggestions: hit.suggestions.map((p) => p.name), note: hit.note };
    });
    // A player at 0 who was not at 0 last week: a reason from what get-values has (the trade charts, projections).
    const zeros = results.filter((r) => r.player && r.player.value <= ZERO);
    const reasons = new Map<number, { before: number; reason: string; week: number | null }>();
    if (zeros.length && finderDeps?.analysis?.fetchAnalysis) {
      try {
        const prior = await finderDeps.analysis.fetchAnalysis(s.scoring, s.teams, s.superflex, s.league, null, ["series", "prior"]);
        const rows = new Map(pageRows(prior).map((r) => [r.player_key, r]));
        const was = prior.prior?.series?.ddf_value?.values ?? {};
        for (const z of zeros) {
          const before = was[String(z.player!.player_key)];
          const row = rows.get(z.player!.player_key);
          if (!(before > ZERO) || !row) continue;
          reasons.set(z.player!.player_key, { before: round1(before), reason: moveReason(prior, row, before, z.player!.value) ?? "", week: prior.prior?.prior_week ?? null });
        }
      } catch (e) {
        console.error("get_player_value: prior week unavailable:", String((e as Error)?.message ?? e));
      }
    }
    const lineOf = (r: typeof results[number]) => {
      if (!r.player) return r.note || `${r.input}: NOT FOUND`;
      const why = reasons.get(r.player.player_key);
      const was = why ? ` (was ${why.before}${why.week ? ` in Week ${why.week}` : " last week"}${why.reason ? `; ${why.reason}` : ""})` : "";
      return `${r.player.name} (${r.player.pos}): value ${r.player.value}, tier ${r.player.tier}${was}${r.note ? ` — ${r.note}` : ""}`;
    };
    const text = [...header(data, s), "", ...results.map(lineOf)].join("\n");
    const found = results.filter((r) => r.player);
    const summary = results.length === 1
      ? (found.length ? `${lineOf(results[0]).replace(/: value /, " is worth ").replace(/, tier /, " DDF Value, tier ")}.`.replace(/\.\.$/, ".") : lineOf(results[0]))
      : `${found.map((r) => `${r.player!.name} ${r.player!.value}`).join(", ") || "No player found"}${found.length < results.length ? `; ${results.length - found.length} not found or unclear` : ""}.`;
    const first = results.find((r) => r.player);
    return finish(ok(text, {
      as_of: data.as_of, setting: data.setting,
      results: results.map((r) => {
        const why = r.player ? reasons.get(r.player.player_key) : undefined;
        return why ? { ...r, prior_value: why.before, reason: why.reason || null } : r;
      }),
    }), {
      prepared, deps, settings: s, view: "targets", summary,
      work: first ? { target: entry(first.input, first.player) } : undefined,
    });
  }

  if (name === "trade_targets") {
    const pos = position(args);
    const pct = parseBounded(args.range_pct, "range_pct", 15, 1, 50);
    const query = String(args.player_name ?? "").trim();
    if (!query) {
      if (!hasLeagueInput(args)) {
        throw new ToolInputError("player_name is required, or give the league (league_paste or league_teams with my_team, or a state that saved it) for your weakest starting slot.");
      }
      return await teamTargets(args, s, fetchValues, prepared, deps);
    }
    checkName(query, "player_name");
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const hit = matchName(data.players, query);
    if (hit.match === "ambiguous" || !hit.player) {
      return {
        content: [{ type: "text", text: `${data.attribution}\n\n${hit.note || `Player "${query}" not found.`}` }],
        isError: true,
      };
    }
    const player = hit.player;
    const range = player.value * (pct / 100);
    const pool = data.players.filter((p) => p.player_key !== player.player_key && (pos === "all" || p.pos === pos));
    const targets = pool
      .filter((p) => Math.abs(p.value - player.value) <= range)
      .sort((a, b) => Math.abs(a.value - player.value) - Math.abs(b.value - player.value))
      .slice(0, 20)
      .map((p) => ({ ...p, diff: Math.round((p.value - player.value) * 10) / 10 }));
    const who = pos === "all" ? "player" : pos;
    let summary: string;
    let nearest: (PlayerValue & { diff: number; range_pct_needed: number }) | null = null;
    if (targets.length) {
      const t = targets[0];
      summary = `${targets.length} ${who}${targets.length === 1 ? "" : "s"} within ${pct}% of ${player.name} (${player.value}); closest: ${t.name} (${t.pos} ${t.value}).`;
    } else {
      // Connector walkthrough 2026-11-21: an empty result says why and what to try.
      const near = pool.slice().sort((a, b) => Math.abs(a.value - player.value) - Math.abs(b.value - player.value))[0];
      if (near) {
        const needed = player.value > 0 ? Math.abs(near.value - player.value) / player.value * 100 : Infinity;
        const tryPct = Math.min(50, Math.ceil((needed + 0.01) / 5) * 5);
        nearest = { ...near, diff: round1(near.value - player.value), range_pct_needed: round1(needed) };
        summary = `No ${who} within ${pct}% of ${player.name} (${player.value}). Nearest: ${near.name} (${near.pos}) at ${near.value}.` +
          (needed <= 50 ? ` Try range_pct ${tryPct}.` : " That is more than 50% away, so a 1-for-1 at this value is unlikely.");
      } else {
        summary = `No other ${who} is priced for these settings.`;
      }
    }
    const text = [
      ...header(data, s),
      "",
      `Trade targets for ${player.name} (${player.pos}, value ${player.value}, tier ${player.tier}):`,
      ...(targets.length
        ? ["Player | Pos | Value | Tier | Diff", ...targets.map((t) => `${t.name} | ${t.pos} | ${t.value} | ${t.tier} | ${t.diff >= 0 ? "+" : ""}${t.diff.toFixed(1)}`)]
        : ["  none in range"]),
    ].join("\n");
    return finish(ok(text, { as_of: data.as_of, setting: data.setting, player, targets, ...(nearest ? { nearest } : {}) }), {
      prepared, deps, settings: s, view: "targets", work: { target: entry(String(args.player_name), player) }, summary,
    });
  }

  if (name === "compare_trade") {
    // Connector walkthrough 2026-11-21: give/get speak for the user; side_a/side_b stay as older names.
    const giveRaw = args.give ?? args.side_a;
    const getRaw = args.get ?? args.side_b;
    const namesA = playerNames(giveRaw, args.give !== undefined ? "give" : "side_a");
    const namesB = playerNames(getRaw, args.get !== undefined ? "get" : "side_b");
    if (!namesA.length || !namesB.length) {
      throw new ToolInputError("give and get each need at least one name (what the user gives, what the user gets).");
    }
    const bySource = parseBool(args.by_source, "by_source", false);
    const data: AnalysisResponse = bySource
      ? await analysisData(finderDeps?.analysis, "trade", s, ["series"])
      : await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    let a = resolveNames(data.players, namesA);
    let b = resolveNames(data.players, namesB);
    stopOnUnresolved(data.players, a, b);
    // The same player on both sides stays on the give side, matching the site.
    const giveKeys = new Set(a.matched.map((p) => p.player_key));
    const shared = b.matched.filter((p) => giveKeys.has(p.player_key));
    if (shared.length) {
      b = {
        ...b,
        matched: b.matched.filter((p) => !giveKeys.has(p.player_key)),
        notes: [...b.notes, `On both sides, kept on the give side only: ${shared.map((p) => p.name).join(", ")}.`],
      };
    }
    if (!a.matched.length || !b.matched.length) {
      const why = [...nameLines([{ res: a }, { res: b }]), ...a.notes, ...b.notes].filter(Boolean).join(" ");
      throw new ToolInputError(why || "give and get each need at least one matched player");
    }
    // Every name matched (stopOnUnresolved), so the link carries keys only (JEG-1124).
    const work = {
      give: a.matched.map((p) => entry(p.name, p)),
      get: b.matched.map((p) => entry(p.name, p)),
    };
    const lineup = lineupChange(args, s, data.players, a.matched, b.matched, deps);
    const notes = nameLines([{ res: a }, { res: b }]);
    if (bySource) {
      const out = compareBySource(data, s, a, b, finderDeps!.analysis!.modules!.trade, lineup, notes);
      return finish(out.result, { prepared, deps, settings: s, view: "compare", work, summary: out.summary });
    }
    const sum = (rows: PlayerValue[]) => round1(rows.reduce((t, p) => t + p.value, 0));
    const sumA = sum(a.matched);
    const sumB = sum(b.matched);
    const diff = round1(sumA - sumB);
    const net = round1(sumB - sumA);
    const verdict = net === 0
      ? "even"
      : Math.abs(diff) < 2
      ? `roughly even (you ${net >= 0 ? "gain" : "lose"} ${Math.abs(net).toFixed(1)})`
      : net > 0
      ? `you win by ${net.toFixed(1)}`
      : `you lose by ${(-net).toFixed(1)}`;
    const summary = net === 0
      ? `Even by DDF Value (give ${sumA.toFixed(1)}, get ${sumB.toFixed(1)}).`
      : Math.abs(diff) < 2
      ? `Roughly even by DDF Value: you ${net >= 0 ? "gain" : "lose"} ${Math.abs(net).toFixed(1)} (give ${sumA.toFixed(1)}, get ${sumB.toFixed(1)}).`
      : `You ${net > 0 ? "win" : "lose"} ${Math.abs(net).toFixed(1)} by DDF Value (give ${sumA.toFixed(1)}, get ${sumB.toFixed(1)}).`;
    const fmt = (rows: PlayerValue[]) => rows.map((p) => `  ${p.name} (${p.pos}): ${p.value}`).join("\n");
    const text = [
      ...header(data, s),
      ...(lineup ? [lineup.line] : []),
      ...notes,
      "",
      `You give (total ${sumA.toFixed(1)}):`,
      fmt(a.matched),
      `You get (total ${sumB.toFixed(1)}):`,
      fmt(b.matched),
      "",
      "Verdict: DDF Value sum, not lineup-aware (a gap under 2 points counts as roughly even, a rule of thumb). The site's Compare a trade shows the per-chart breakdown; open the link below.",
    ].join("\n");
    // Every name matched (stopOnUnresolved), so not_found stays empty; kept for the reply's shape.
    const pack = (rows: PlayerValue[]) => ({
      total: sum(rows),
      players: rows.map((p) => ({ name: p.name, pos: p.pos, value: p.value })),
      not_found: [] as string[],
    });
    // The site's Compare a trade reads "give" as what the person gives up: side_a is the person's give.
    return finish(
      ok(text, {
        as_of: data.as_of,
        setting: data.setting,
        side_a: pack(a.matched),
        side_b: pack(b.matched),
        difference: diff,
        net_for_you: net,
        verdict,
        method: "sum_of_ddf_values",
        ...(lineup ? { lineup: lineup.structured } : {}),
        not_found: [],
      }),
      { prepared, deps, settings: s, view: "compare", work, summary },
    );
  }

  throw new ToolInputError(`unknown tool: ${name}`);
}

// ---------- JEG-1029: risers_fallers, compare_trade by_source, audit_values ----------
// get-values prices; the page's own modules (movers.js, trade.js, audit-pie.js, audit-source.js) read
// what it returns exactly as the page reads its engine. See analyses.ts.

type Settings = ReturnType<typeof settings>;
const MODULE_FOR = { risers: "movers", trade: "trade", health: "auditPie", source: "auditSource" } as const;

async function analysisData(
  analysis: AnalysisDeps | undefined, use: keyof typeof MODULE_FOR, s: Settings, includes: string[],
): Promise<AnalysisResponse> {
  const module = analysis?.modules?.[MODULE_FOR[use]];
  if (!analysis?.fetchAnalysis || !module) {
    throw new ToolUnavailableError("This analysis is unavailable right now (the site's module could not be loaded). Open the site link instead.");
  }
  return await analysis.fetchAnalysis(s.scoring, s.teams, s.superflex, s.league, null, includes);
}

const seriesName = (key: string) => SERIES_LABELS[key] ?? key;

// ---------- reasons for a big move or a drop to 0 (connector walkthrough 2026-11-21, part B) ----------
// get-values sends no injury status, so a reason is read only from what it does send: each trade chart's value this
// week and last (include=series, prior) and the projections. Never an injury claim.
const TRADE_CHARTS = ["fantasycalc", "usatoday", "fantasypros", "cbs"];
/** A value at or under this is 0 (replacement level). */
const ZERO = 0.05;
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function moveReason(data: AnalysisResponse, row: PageRow, before: number, now: number, move = 2.5): string | null {
  const key = String(row.player_key);
  const entry = (k: string) => (data.prior?.series?.[k]?.available ? data.prior.series[k] : null);
  const priorOf = (k: string) => entry(k)?.values?.[key];
  const nowOf = (k: string) => entry(k)?.current_values?.[key] ?? row.values?.[k];
  const charts = TRADE_CHARTS.filter((k) => !data.sources_included?.length || data.sources_included.includes(k));
  const pNow = row.values?.ddf_value_projections;
  const pWas = priorOf("ddf_value_projections");
  const proj = isNum(pNow) && isNum(pWas) ? `projections ${round1(pWas)} -> ${round1(pNow)}` : isNum(pNow) ? `projections ${round1(pNow)}` : "";
  if (now <= ZERO && before > ZERO) {
    const listed = charts.filter((k) => isNum(row.values?.[k]));
    const atZero = listed.filter((k) => (row.values[k] ?? 0) <= ZERO).length;
    const head = !listed.length
      ? "no trade chart lists him this week"
      : atZero === listed.length
      ? "every trade chart has him at 0 this week"
      : `${atZero} of ${listed.length} trade charts have him at 0 this week`;
    return `${head} (often an injury or a role change; check the news)${proj ? `; ${proj}` : ""}`;
  }
  if (Math.abs(now - before) < move) return null;
  const up = now > before;
  const both = charts.filter((k) => isNum(nowOf(k)) && isNum(priorOf(k)));
  const same = both.filter((k) => (up ? nowOf(k)! - priorOf(k)! : priorOf(k)! - nowOf(k)!) > 0).length;
  const parts = [
    ...(both.length ? [`${same} of ${both.length} trade charts ${up ? "up" : "down"}`] : []),
    ...(proj ? [proj] : []),
  ];
  return parts.length ? parts.join("; ") : null;
}

/** Who has each player in the league: "yours", the team's name, or (not on any roster) "free agent". */
function ownersOf(league: LeagueRead | null, players: PlayerValue[]): ((key: number) => string) | null {
  if (!league) return null;
  const owner = new Map<number, string>();
  league.teams.forEach((t, i) => {
    for (const p of resolveNames(players, t.players).matched) {
      if (!owner.has(p.player_key)) owner.set(p.player_key, i === league.mine ? "yours" : t.name);
    }
  });
  return (key) => owner.get(key) ?? "free agent";
}

function compareBySource(
  data: AnalysisResponse, s: Settings, a: ResolvedNames<PlayerValue>, b: ResolvedNames<PlayerValue>,
  // deno-lint-ignore no-explicit-any
  trade: any,
  lineup: LineupChange | null,
  nameNotes: string[],
): { result: ToolResult; summary: string } {
  const rowsByKey = new Map(pageRows(data).map((row) => [row.player_key, row]));
  // A player get-values has no row for comes in with no values, so every series reads it as missing.
  const rowsOf = (list: PlayerValue[]) => list.map((p) => rowsByKey.get(p.player_key) ?? { player_key: p.player_key, name: p.name, pos: p.pos, values: {} });
  const giveRows = rowsOf(a.matched);
  const getRows = rowsOf(b.matched);
  const { rows } = trade.compareTrade(giveRows, getRows, COMPARE_SERIES);
  const verdict = trade.tradeVerdict(rows, "ddf_value");
  // deno-lint-ignore no-explicit-any
  const slim = rows.map((r: any) => ({
    series: r.key, label: seriesName(r.key),
    give: r.give === null ? null : round1(r.give), get: r.receive === null ? null : round1(r.receive),
    net: r.net === null ? null : round1(r.net),
    // deno-lint-ignore no-explicit-any
    missing: r.missing.map((m: any) => ({ name: m.row.name, side: m.side === "give" ? "a" : "b" })),
  }));
  const names = (keys: string[]) => keys.map(seriesName).join(", ");
  const net = verdict.net === null || verdict.net === undefined ? null : Math.abs(verdict.net);
  const verdictText = verdict.kind === "win"
    ? `you win by ${net!.toFixed(1)} on DDF Value`
    : verdict.kind === "lose"
    ? `you lose by ${net!.toFixed(1)} on DDF Value`
    : verdict.kind === "even"
    ? "even on DDF Value"
    : "DDF Value cannot be read: a player has no DDF Value";
  const against = verdict.againstKeys?.length ? `Pointing the other way: ${names(verdict.againstKeys)}.` : null;
  const agree = verdict.kind && verdict.kind !== "incomplete" && verdict.others
    ? `${verdict.agreeKeys.length} of ${verdict.others} chart${verdict.others === 1 ? "" : "s"} agree.` : null;
  const incomplete = verdict.incompleteKeys?.length ? `Not read (a player is missing there): ${names(verdict.incompleteKeys)}.` : null;
  // deno-lint-ignore no-explicit-any
  const ddf = slim.find((r: any) => r.series === "ddf_value");
  const sums = ddf && ddf.give !== null && ddf.get !== null ? ` (give ${ddf.give.toFixed(1)}, get ${ddf.get.toFixed(1)})` : "";
  const head = verdict.kind === "win" || verdict.kind === "lose"
    ? `You ${verdict.kind} ${net!.toFixed(1)} by DDF Value${sums}.`
    : verdict.kind === "even"
    ? `Even by DDF Value${sums}.`
    : "DDF Value cannot be read for this trade: a player has no DDF Value.";
  const summary = [head, agree].filter(Boolean).join(" ");
  const notFound = [...a.unmatched, ...b.unmatched];
  const text = [
    ...header(data, s),
    ...(lineup ? [lineup.line] : []),
    ...nameNotes,
    "",
    `You give: ${a.matched.map((p) => p.name).join(", ")}`,
    `You get: ${b.matched.map((p) => p.name).join(", ")}`,
    "Series | You give | You get | Net for you",
    // deno-lint-ignore no-explicit-any
    ...slim.map((r: any) => r.net === null
      ? `${r.label} | — | — | — (no value: ${r.missing.map((m: { name: string }) => m.name).join(", ")})`
      : `${r.label} | ${r.give.toFixed(1)} | ${r.get.toFixed(1)} | ${fmtNet(r.net)}`),
    "",
    `Verdict (DDF Value decides; the charts are a second opinion): ${verdictText}.`,
    ...[against, incomplete].filter(Boolean) as string[],
    ...(notFound.length ? [`Warning: not found, left out: ${notFound.join(", ")}`] : []),
  ].join("\n");
  return {
    summary,
    result: ok(text, {
      as_of: data.as_of, setting: data.setting, method: "compare_trade_by_series", rows: slim,
      verdict: { kind: verdict.kind, series: "ddf_value", net: verdict.net === null || verdict.net === undefined ? null : round1(verdict.net),
        agree: verdict.agreeKeys ?? [], against: verdict.againstKeys ?? [], incomplete: verdict.incompleteKeys ?? [] },
      ...(lineup ? { lineup: lineup.structured } : {}),
      not_found: notFound,
    }),
  };
}

// ---------- trade_targets for the team (connector walkthrough 2026-11-21, part B) ----------

const median = (xs: number[]) => {
  const v = xs.slice().sort((a, b) => a - b);
  if (!v.length) return 0;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
};

/**
 * The user's weakest starting slot and who would upgrade it. Each team's starters come from the finder's lineup pick
 * (viability.ts pickStarters) on DDF Values; at each position the user's lowest starter is set against the league's
 * typical starter there (the median of every team's starters at that position). The largest shortfall is the weakest
 * slot; the upgrades are players at that position on other rosters worth more than the user's starter, closest first.
 */
async function teamTargets(
  args: Record<string, unknown>, s: Settings, fetchValues: FetchValues, prepared: Prepared, deps?: Deps,
): Promise<ToolResult> {
  const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
  const league = leagueOf(args, data.players, deps)!;
  const me = myTeamOf(league);
  const shape = shapeOf(args, s);
  const resolved = league.teams.map((t) => resolveNames(data.players, t.players));
  const teams = resolved.map((r) => r.matched);
  const picks = teams.map((rows) => pickStarters(rows.map(lineupRow), shape, "ddf_value"));
  const want = position(args);
  const slots = (["QB", "RB", "WR", "TE"] as const).filter((p) => shape[p] > 0 && (want === "all" || want === p));
  const gaps = slots.map((p) => {
    const mine = picks[me].slots[p] ?? [];
    // An empty starting slot counts as 0.
    const weakest = mine.length < shape[p] ? null : mine[mine.length - 1];
    const weakestValue = weakest ? weakest.values.ddf_value ?? 0 : 0;
    const typical = median(picks.flatMap((pk) => (pk.slots[p] ?? []).map((r) => r.values.ddf_value ?? 0)));
    return { pos: p, weakest, weakestValue, typical, gap: typical - weakestValue };
  }).sort((a, b) => b.gap - a.gap);
  const worst = gaps[0];
  const lines: string[] = [...header(data, s), ""];
  const myName = league.teams[me].name;
  lines.push(`Your team: ${myName}. Starting slots against the league's typical starter (DDF Value):`);
  lines.push(...gaps.map((g) => `  ${g.pos}: your weakest ${g.weakest ? `${g.weakest.name} ${round1(g.weakestValue)}` : "empty slot 0"}, typical ${round1(g.typical)} (${signed(round1(g.weakestValue - g.typical))})`));
  let summary: string;
  let upgrades: Array<{ name: string; pos: string; value: number; tier: string; team: string; gain: number }> = [];
  if (!worst || worst.gap <= 0) {
    summary = `Every starting slot on ${myName} is at or above the league's typical starter, so there is no weak slot to fill.`;
  } else {
    upgrades = teams.flatMap((rows, i) => i === me ? [] : rows.filter((p) => p.pos === worst.pos && p.value > worst.weakestValue)
      .map((p) => ({ name: p.name, pos: p.pos, value: p.value, tier: p.tier, team: league.teams[i].name, gain: round1(p.value - worst.weakestValue) })))
      .sort((a, b) => a.value - b.value)
      .slice(0, 15);
    const who = worst.weakest ? `${worst.pos} ${worst.weakest.name} (${round1(worst.weakestValue)})` : `your empty ${worst.pos} slot`;
    summary = upgrades.length
      ? `Your weakest starter is ${who}; a typical ${worst.pos} starter here is ${round1(worst.typical)}. ${upgrades.length} ${worst.pos}${upgrades.length === 1 ? "" : "s"} on other teams would upgrade it; closest: ${upgrades[0].name} (${upgrades[0].team}, ${upgrades[0].value}).`
      : `Your weakest starter is ${who}, but no ${worst.pos} on another team is worth more.`;
    if (upgrades.length) {
      lines.push("", `${worst.pos}s on other teams who would upgrade it, closest value first:`, "Player | Team | Value | Tier | Gain");
      lines.push(...upgrades.map((u) => `${u.name} | ${u.team} | ${u.value} | ${u.tier} | +${u.gain.toFixed(1)}`));
    }
  }
  const notes = nameLines(resolved.map((res, i) => ({ res, team: i === me ? undefined : league.teams[i].name })), league);
  lines.push(...(notes.length ? ["", ...notes] : []));
  return finish(ok(lines.join("\n"), {
    as_of: data.as_of, setting: data.setting, my_team: myName,
    slots: gaps.map((g) => ({ pos: g.pos, weakest: g.weakest?.name ?? null, weakest_value: round1(g.weakestValue), typical: round1(g.typical), gap: round1(g.gap) })),
    weakest: worst && worst.gap > 0 ? worst.pos : null,
    targets: upgrades,
  }), { prepared, deps, settings: s, view: "targets", summary });
}

// ---------- the user's starting lineup (compare_trade, trade_targets) ----------

/** The lineup shape for the user's league: roster_shape, else this call's slots, else the slots a state saved. */
function shapeOf(args: Record<string, unknown>, s: Settings): RosterShape {
  return rosterShape(args, s.superflex, s.roster ?? (s.league?.roster as Record<string, number> | undefined) ?? null);
}

const lineupRow = (p: PlayerValue): ViabilityRow => ({ player_key: p.player_key, name: p.name, pos: p.pos, values: { ddf_value: p.value } });
const starterValue = (rows: ViabilityRow[]) => rows.reduce((t, r) => t + (r.values.ddf_value ?? 0), 0);

/** The user's roster names: mine, else their team in a league (league_paste, league_teams or a state). Null when unknown. */
function userRosterNames(args: Record<string, unknown>, players: PlayerValue[], deps?: Deps): string[] | null {
  const mine = playerNames(args.mine, "mine");
  if (mine.length) return mine;
  if (!hasLeagueInput(args)) return null;
  const league = leagueOf(args, players, deps);
  return league && league.mine !== null ? league.teams[league.mine].players : null;
}

interface LineupChange {
  line: string;
  /** pos is the lineup slot (QB, RB, WR, TE, FLEX, SUPERFLEX). */
  structured: { delta: number; changes: Array<{ pos: string; out: string | null; out_value: number | null; in: string | null; in_value: number | null }>; not_on_roster: string[] };
}

/**
 * Connector walkthrough 2026-11-21 (part B): how a trade moves the user's starting lineup, by the finder's own
 * lineup pick (viability.ts pickStarters) on DDF Values. Null when the user's roster is not known.
 */
function lineupChange(
  args: Record<string, unknown>, s: Settings, players: PlayerValue[], give: PlayerValue[], get: PlayerValue[], deps?: Deps,
): LineupChange | null {
  const names = userRosterNames(args, players, deps);
  if (!names) return null;
  const roster = resolveNames(players, names).matched.map(lineupRow);
  if (!roster.length) return null;
  const shape = shapeOf(args, s);
  const onRoster = new Set(roster.map((r) => r.player_key));
  const notOn = give.filter((p) => !onRoster.has(p.player_key)).map((p) => p.name);
  const beforePick = pickStarters(roster, shape, "ddf_value");
  const afterPick = pickStarters(applyTrade(roster, give.map(lineupRow), get.filter((p) => !onRoster.has(p.player_key)).map(lineupRow)), shape, "ddf_value");
  const before = beforePick.starters;
  const after = afterPick.starters;
  const delta = round1(starterValue(after) - starterValue(before));
  const slotOf = (pick: typeof beforePick) => {
    const m = new Map<number, string>();
    for (const [slot, list] of Object.entries(pick.slots)) for (const r of list) m.set(r.player_key, slot);
    return m;
  };
  const beforeSlot = slotOf(beforePick);
  const afterSlot = slotOf(afterPick);
  const outs = before.filter((r) => !afterSlot.has(r.player_key));
  const ins = after.filter((r) => !beforeSlot.has(r.player_key));
  const changes: LineupChange["structured"]["changes"] = [];
  // Pair each new starter with the starter who left the same slot (else the same position, else any).
  for (const inRow of ins) {
    const slot = afterSlot.get(inRow.player_key)!;
    let i = outs.findIndex((o) => beforeSlot.get(o.player_key) === slot);
    if (i < 0) i = outs.findIndex((o) => o.pos === inRow.pos);
    if (i < 0 && outs.length) i = 0;
    const outRow = i >= 0 ? outs.splice(i, 1)[0] : null;
    changes.push({ pos: slot, out: outRow?.name ?? null, out_value: outRow ? round1(outRow.values.ddf_value ?? 0) : null, in: inRow.name, in_value: round1(inRow.values.ddf_value ?? 0) });
  }
  for (const o of outs) changes.push({ pos: beforeSlot.get(o.player_key)!, out: o.name, out_value: round1(o.values.ddf_value ?? 0), in: null, in_value: null });
  const said = changes.map((c) => c.out && c.in
    ? `${c.pos} ${c.out} ${c.out_value} -> ${c.in} ${c.in_value}`
    : c.in ? `${c.pos} ${c.in} ${c.in_value} starts` : `${c.pos} ${c.out} ${c.out_value} leaves an empty slot`);
  const line = `Your starting lineup: ${signed(delta)} (${said.length ? said.join(", ") : "no starter changes"})` +
    `${notOn.length ? `; not on your roster: ${notOn.join(", ")}` : ""}.`;
  return { line, structured: { delta, changes, not_on_roster: notOn } };
}

async function risersFallersHandler(args: Record<string, unknown>, deps?: Deps, analysis?: AnalysisDeps): Promise<ToolResult> {
  const prepared = prepare(args, deps);
  args = prepared.args;
  const s = settings(args);
  const series = String(args.series ?? "ddf_value");
  if (!MOVERS_SERIES.includes(series)) {
    throw new ToolInputError(`invalid series: ${series}. Must be one of: ${MOVERS_SERIES.join(", ")}`);
  }
  const pos = position(args);
  const limit = parseBounded(args.limit, "limit", 10, 1, 25);
  const withDisagreements = parseBool(args.disagreements, "disagreements", true);
  const data = await analysisData(analysis, "risers", s, ["series", "prior"]);
  const M = analysis!.modules!.movers;
  const rows = pageRows(data).filter((r) => pos === "all" || r.pos === pos);
  const v = M.buildMovers(rows, series, priorFor(data, series));
  const label = seriesName(series);
  // Connector walkthrough 2026-11-21: with the league, each row says who has the player.
  const owner = hasLeagueInput(args) ? ownersOf(leagueOf(args, data.players, deps), data.players) : null;
  const rowByKey = new Map(rows.map((r) => [r.player_key, r]));
  // A reason for a drop to 0 or a big move, on the DDF Value series (the trade charts' average).
  const reasonFor = (key: number, before: number, now: number) => {
    const row = rowByKey.get(key);
    return row && (series === "ddf_value" || series === "ddf_value_charts") ? moveReason(data, row, before, now, M.MOVE ?? 2.5) : null;
  };
  // deno-lint-ignore no-explicit-any
  const tagged = (m: any) => {
    const slim = slimMover(m);
    const reason = reasonFor(slim.player_key, m.before, m.current);
    return { ...slim, ...(owner ? { owner: owner(slim.player_key) } : {}), ...(reason ? { reason } : {}) };
  };
  const risers = v.risers.slice(0, limit).map(tagged);
  const fallers = v.fallers.slice(0, limit).map(tagged);
  const line = (m: ReturnType<typeof tagged>) =>
    `${m.name} (${m.pos}${m.owner ? `, ${m.owner}` : ""}): ${m.before.toFixed(1)} → ${m.now.toFixed(1)} (${fmtNet(m.delta)})${m.reason ? ` — ${m.reason}` : ""}`;
  const text: string[] = [...header(data, s), ""];
  const summary = !v.available
    ? `No change to show for ${label}: ${v.reason}.`
    : !risers.length && !fallers.length
    ? `No ${label} changes from Week ${v.priorWeek} to Week ${v.currentWeek}${pos === "all" ? "" : ` at ${pos}`}.`
    : `Week ${v.priorWeek} to ${v.currentWeek}${pos === "all" ? "" : `, ${pos}`}: ${[
      risers[0] ? `biggest riser ${risers[0].name} ${fmtNet(risers[0].delta)}${risers[0].owner ? ` (${risers[0].owner})` : ""}` : "",
      fallers[0] ? `biggest faller ${fallers[0].name} ${fmtNet(fallers[0].delta)}${fallers[0].owner ? ` (${fallers[0].owner})` : ""}` : "",
    ].filter(Boolean).join("; ")}.`;
  if (v.available) {
    text.push(`${label}: Week ${v.priorWeek} → Week ${v.currentWeek}, both priced for this league.`);
    text.push(`Risers (${v.risers.length}):`, ...(risers.length ? risers.map(line) : ["  none"]));
    text.push(`Fallers (${v.fallers.length}):`, ...(fallers.length ? fallers.map(line) : ["  none"]));
    const counts = [`${v.compared} compared`];
    if (v.unchanged) counts.push(`${v.unchanged} unchanged (0.0)`);
    if (v.noPrior) counts.push(`${v.noPrior} not priced in Week ${v.priorWeek}, so no change`);
    if (v.noCurrent) counts.push(`${v.noCurrent} without a Week ${v.currentWeek} value`);
    text.push(`Players: ${counts.join(", ")}. Missing history is no change, never a zero change.`);
  } else {
    text.push(`No change to show for ${label}: ${v.reason}.`);
  }
  // deno-lint-ignore no-explicit-any
  let disagreements: any = null;
  if (withDisagreements) {
    const d = M.buildDisagreements(rows, priorFor(data, "ddf_value_charts"), priorFor(data, "ddf_value_projections"));
    // deno-lint-ignore no-explicit-any
    const taggedD = (x: any) => {
      const slim = slimDisagreement(x);
      // A market drop to 0 is often news the projections have not caught; the reason says so before the "buy".
      const reason = x.market.current <= ZERO && x.market.before > ZERO ? moveReason(data, x.row, x.market.before, x.market.current) : null;
      return { ...slim, ...(owner ? { owner: owner(slim.player_key) } : {}), ...(reason ? { reason } : {}) };
    };
    disagreements = d.available
      ? { available: true, compared: d.compared, market: d.market.slice(0, limit).map(taggedD),
        projections: d.projections.slice(0, limit).map(taggedD), market_total: d.market.length, projections_total: d.projections.length }
      : { available: false, reason: d.reason };
    text.push("");
    if (d.available) {
      const dl = (x: ReturnType<typeof taggedD>) =>
        `${x.name} (${x.pos}${x.owner ? `, ${x.owner}` : ""}): DDF Value ${fmtNet(x.market_delta)}, projections ${fmtNet(x.projections_delta)}. ${x.reason ? `${x.reason[0].toUpperCase()}${x.reason.slice(1)}, so read this first: ` : ""}${x.read}`;
      text.push(`Market vs projections, Week ${d.priorWeek} → Week ${d.currentWeek} (one moved ${M.MOVE}+ and the other ${M.QUIET.toFixed(1)} or less; ${d.compared} compared):`);
      text.push(`Market moved (${d.market.length}):`, ...(disagreements.market.length ? disagreements.market.map(dl) : ["  none"]));
      text.push(`Projections moved (${d.projections.length}):`, ...(disagreements.projections.length ? disagreements.projections.map(dl) : ["  none"]));
    } else {
      text.push(`Market vs projections: no comparison yet: ${d.reason}.`);
    }
  }
  return finish(ok(text.join("\n"), {
    as_of: data.as_of, setting: data.setting, series, position: pos, available: v.available,
    reason: v.available ? null : v.reason, current_week: v.currentWeek ?? null, prior_week: v.priorWeek ?? null,
    risers, fallers, counts: { compared: v.compared, unchanged: v.unchanged, no_prior: v.noPrior, no_current: v.noCurrent,
      risers: v.risers.length, fallers: v.fallers.length },
    disagreements,
  }), { prepared, deps, settings: s, view: "risers", summary });
}

async function auditValuesHandler(args: Record<string, unknown>, deps?: Deps, analysis?: AnalysisDeps): Promise<ToolResult> {
  const prepared = prepare(args, deps);
  args = prepared.args;
  const s = settings(args);
  const viewName = String(args.view ?? "health");
  if (viewName !== "health" && viewName !== "source") throw new ToolInputError(`invalid view: ${viewName}. Must be health or source`);
  const data = await analysisData(analysis, viewName, s, ["audit"]);
  const inspection = inspectionOf(data);
  const text: string[] = [...header(data, s), ""];
  if (viewName === "health") {
    const P = analysis!.modules!.auditPie;
    const model = P.extract(inspection);
    if (!model) {
      return finish(ok(text.join("\n"), { as_of: data.as_of, setting: data.setting, view: "health", available: false, checks: [] }),
        { prepared, deps, settings: s, view: "audit", summary: "Health check: no pipeline data available." });
    }
    P.computeFlags(model);
    const checks = P.computeChecks(model);
    // deno-lint-ignore no-explicit-any
    const slim = checks.map((c: any) => ({ id: c.id, label: c.name, status: c.status, detail: c.reason ?? null, sources: c.sources ?? [] }));
    // deno-lint-ignore no-explicit-any
    const flagged = slim.filter((c: any) => c.status === "flag");
    // deno-lint-ignore no-explicit-any
    const summary = `Health check: ${flagged.length ? `${flagged.length} of ${slim.length} checks flagged (${flagged.map((c: any) => c.label).join(", ")})` : `all ${slim.length} checks pass`}.`;
    text.push(`Value pie ${round1(model.pie)} points, ${model.rows.length} sources.`);
    // deno-lint-ignore no-explicit-any
    text.push(...slim.map((c: any) => `${c.status.toUpperCase()} | ${c.label}${c.detail ? ` | ${c.detail}` : ""}`));
    return finish(ok(text.join("\n"), {
      as_of: data.as_of, setting: data.setting, view: "health", available: true, pie: round1(model.pie), sources: model.rows.length, checks: slim,
    }), { prepared, deps, settings: s, view: "audit", summary });
  }
  const source = String(args.source ?? "fantasycalc");
  if (!AUDIT_SOURCES.includes(source)) throw new ToolInputError(`invalid source: ${source}. Must be one of: ${AUDIT_SOURCES.join(", ")}`);
  const pos = position(args);
  const limit = parseBounded(args.limit, "limit", 15, 1, 50);
  const m = analysis!.modules!.auditSource.build(inspection, source, pos === "all" ? "ALL" : pos);
  const val = (v: number | null) => v === null ? "—" : v.toFixed(1);
  // A stage with no points has no total: null, never 0 (the page draws nothing for it).
  const total = (stage: string) => m.stages[stage].exists ? round1(m.totals[stage]) : null;
  const totals = { published: total("published"), indexed: total("indexed"), adjusted: total("adjusted") };
  if (!m.hasData) {
    // The page's line for a source with no values (audit-source.js render), and nothing else.
    return finish(ok(text.join("\n"), {
      as_of: data.as_of, setting: data.setting, view: "source", source, position: pos, available: false, status: m.status || null,
      shown: 0, estimated: 0, totals, rows: [],
    }), { prepared, deps, settings: s, view: "audit", summary: `${m.label} has no values at these league settings${m.status ? ` (${m.status})` : ""}.` });
  }
  // deno-lint-ignore no-explicit-any
  const rows = m.rows.slice(0, limit).map((r: any) => ({
    rank: r.rank, player_key: Number(r.key), name: r.name, pos: r.pos, role: r.role, estimated: r.estimated,
    published: r.published === null ? null : round1(r.published), indexed: r.indexed === null ? null : round1(r.indexed),
    adjusted: r.adjusted === null ? null : round1(r.adjusted),
  }));
  text.push(`${m.label} build-up (${m.family}${m.position === "ALL" ? "" : `, ${m.position}`}): ${m.shown} players, ${m.estimatedCount} filled in.` +
    (m.status ? ` Status: ${m.status}.` : ""));
  text.push(`Totals: published ${val(totals.published)} (${m.stages.published.unit}), indexed ${m.stages.indexed.exists ? val(totals.indexed) : "— (" + (m.stages.indexed.reason || "no indexed values") + ")"}, adjusted ${val(totals.adjusted)}.`);
  text.push("Rank | Player | Pos | Role | Published | Indexed | Adjusted");
  // deno-lint-ignore no-explicit-any
  text.push(...rows.map((r: any) => `${r.rank} | ${r.name}${r.estimated ? " (filled in)" : ""} | ${r.pos} | ${r.role} | ${val(r.published)} | ${val(r.indexed)} | ${val(r.adjusted)}`));
  const top = rows[0] ? `; top: ${rows[0].name} (adjusted ${val(rows[0].adjusted)})` : "";
  return finish(ok(text.join("\n"), {
    as_of: data.as_of, setting: data.setting, view: "source", source, position: pos, available: m.hasData, status: m.status || null,
    shown: m.shown, estimated: m.estimatedCount,
    totals,
    rows,
  }), { prepared, deps, settings: s, view: "audit", summary: `${m.label}: ${m.shown} players, adjusted total ${val(totals.adjusted)}${top}.` });
}

// ---------- find_trades tool ----------

/**
 * Convert a ChartPlayerValue into the FinderRow format finder.js expects. The chart keys carry each
 * chart's Indexed value, as the site's rows do in the Indexed view, so the finder's chart checks and
 * the viability market (the mean of the chart keys) read the trade charts' Indexed values. The
 * Adjusted values (chart_values) average to DDF Value itself, so using them would judge the other
 * team on DDF Value and no trade could ever pass (JEG-1129).
 */
export function toFinderRow(p: ChartPlayerValue): FinderRow {
  const values: Record<string, number | null> = {
    ddf_value: p.value,
    ddf_value_charts: p.ddf_value_charts,
    ddf_value_projections: p.ddf_value_projections,
  };
  for (const [k, v] of Object.entries(p.chart_indexed ?? {})) values[k] = v;
  return { player_key: p.player_key, name: p.name, pos: p.pos, values, ddfTier: p.tier };
}

/** The chart players, or unavailable when get-values does not send Indexed chart values yet. */
export function chartPlayersOf(data: { players: ChartPlayerValue[] }): ChartPlayerValue[] {
  const players = data.players ?? [];
  if (players.length && !players.some((p) => p.chart_indexed)) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }
  return players;
}

async function findTradesHandler(
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);

  let mineNames = playerNames(a.mine, "mine");
  let theirNames = playerNames(a.theirs, "theirs");
  const withLeague = hasLeagueInput(a);
  if (!withLeague && !mineNames.length) throw new ToolInputError("mine is required: your roster's names (commas or new lines), or give league_paste or league_teams with my_team.");
  if (!withLeague && !theirNames.length) throw new ToolInputError("theirs is required: their roster's names (commas or new lines), or give a league with my_team and their_team.");
  if (!finderDeps?.finder) {
    throw new ToolUnavailableError("The trade finder is unavailable right now. Try again shortly.");
  }
  if (!finderDeps?.fetchCharts) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }

  const data = await finderDeps.fetchCharts(s.scoring, s.teams, s.superflex, s.league);
  const chartPlayers = chartPlayersOf(data);

  const league = withLeague ? leagueOf(a, chartPlayers, deps) : null;
  let partner: string | null = null;
  if (league) {
    if (!mineNames.length) mineNames = league.teams[myTeamOf(league)].players;
    if (!theirNames.length) {
      const j = partnerOf(league, a.their_team);
      theirNames = league.teams[j].players;
      partner = league.teams[j].name;
    }
  }

  const mineRes = resolveNames(chartPlayers, mineNames);
  const theirRes = resolveNames(chartPlayers, theirNames);
  if (!mineRes.matched.length) throw new ToolInputError(emptyRoster("your roster", mineRes));
  // A player on both rosters stays on yours, so the search cannot trade him for himself.
  const shared = theirRes.matched.filter((p) => mineRes.matched.some((m) => m.player_key === p.player_key));
  const theirMatched = theirRes.matched.filter((p) => !shared.some((p2) => p2.player_key === p.player_key));
  if (!theirMatched.length) {
    throw new ToolInputError(shared.length
      ? `No players left on their roster. Every matched player is also on yours (${shared.map((p) => p.name).join(", ")}), so there is no one to trade for.`
      : emptyRoster("their roster", theirRes));
  }

  const mineRows = mineRes.matched.map(toFinderRow);
  const theirRows = theirMatched.map(toFinderRow);

  const maxPerSide = parseBounded(a.max_per_side, "max_per_side", 2, 1, 4);
  const minRivalEdge = parseNonNegative(a.min_rival_edge, "min_rival_edge", 0);
  const limit = parseBounded(a.limit, "limit", 10, 1, 50);
  // Pull a pool bigger than `limit` so deduping packages that receive the same players can still fill it.
  const pool = Math.min(500, Math.max(limit * 8, limit + 80));

  const result = findTradesForPair(finderDeps.finder, mineRows, theirRows, {
    maxSize: maxPerSide,
    minRivalEdge,
    limit: pool,
  });

  // --- Viability scoring ---
  const shape = rosterShape(a, s.superflex, s.lineup);
  const vConfig = viabilityConfig(a);
  // Decision 4A (2026-11-21): acceptable trades only by default; viable_only=false keeps the full list.
  const viableOnly = parseBool(a.viable_only, "viable_only", true);

  // Build lookup by player_key for full rows.
  const rowByKey = new Map<number, FinderRow>();
  for (const r of mineRows) rowByKey.set(r.player_key, r);
  for (const r of theirRows) rowByKey.set(r.player_key, r);

  const offers: TradeOfferInput[] = result.trades.map((t) => ({
    team: "opponent",
    userGives: t.give.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
    userGets: t.receive.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
    userRoster: mineRows,
    theirRoster: theirRows,
  }));

  const ranked = scoreAndRankOffers(offers, shape, vConfig);
  const viableAll = ranked.filter((o) => o.viable);
  const scored = (viableOnly ? viableAll : ranked).slice(0, limit);
  // JEG-1115: the fit label the finder shows, judged only for the trades returned.
  const finder = finderDeps.finder;
  const fitCtx = fitContextFor(finder, data, shape);
  const trades = scored.map((o) => slimOffer(withFit(o, finder, fitCtx, mineRows, theirRows, rowByKey), false));
  // Decision 4A: none passes every check, so the closest two (fewest failed checks; ranked puts them first) and why.
  const closest = viableOnly && !viableAll.length
    ? ranked.slice(0, 2).map((o) => ({ ...slimOffer(withFit(o, finder, fitCtx, mineRows, theirRows, rowByKey), false), why: failReasons(o) }))
    : [];
  const summary = tradeSummary(trades, closest, viableAll.length, ranked.length, viableOnly, partner ?? "they");

  const nameNotes = [...(league?.notes ?? []), ...nameLines([{ res: mineRes }, { res: theirRes, team: "their roster" }], league)];
  if (partner) nameNotes.unshift(`Trading with ${partner}.`);
  if (shared.length) nameNotes.push(`On both rosters, kept on yours only: ${shared.map((p) => p.name).join(", ")}.`);

  // With no acceptable trade the closest rows are the ones the budget trims (at least one is kept).
  return boundedTrades<typeof closest[number] | typeof trades[number]>(closest.length ? closest : trades, "find_trades", limit, (rows, shortened) => {
    const trades = closest.length ? [] : rows;
    const closestShown = (closest.length ? rows : []) as typeof closest;
    const lines: string[] = [
      ...header(data, s),
      ...nameNotes,
      "",
      foundLine(result.total, trades.length, limit, viableOnly),
      `Your roster: ${mineRes.matched.length} matched, ${missed(mineRes)}; searched ${result.mine.searched} of ${result.mine.of} priced.`,
      `Their roster: ${theirMatched.length} matched, ${missed(theirRes)}; searched ${result.theirs.searched} of ${result.theirs.of} priced.`,
    ];
    if (shortened) lines.push("Fewer candidates shown to keep this reply compact; every returned trade keeps its full fit reason.");
    lines.push("");
    const said = { force: false };
    lines.push(...tradeLines(trades, undefined, said));
    if (closestShown.length) {
      lines.push("Closest (each fails a check, so they would likely say no):");
      lines.push(...tradeLines(closestShown, undefined, said));
      lines.push("Set viable_only to false for every candidate.");
    }

    const structured = {
      as_of: data.as_of,
      setting: data.setting,
      trades,
      total: result.total,
      shown: trades.length,
      limit,
      viableCount: trades.filter((o) => o.viable).length,
      viable_only: viableOnly,
      ...(closestShown.length ? { closest: closestShown } : {}),
      mine: { ...result.mine, unmatched: mineRes.unmatched, ...ambiguousOf(mineRes) },
      theirs: { ...result.theirs, unmatched: theirRes.unmatched, ...ambiguousOf(theirRes) },
    };

    const work = {
      mine: mineNames.map((n) => workEntry(data.players, n)),
      theirs: theirNames.map((n) => workEntry(data.players, n)),
      ...leagueWork(league, data.players),
    };

    return finish(ok(lines.join("\n"), structured), {
      prepared, deps, settings: s, view: "finder", work, summary,
    });
  });
}

/**
 * JEG-1115: the fit context for a chart response. The compared charts are the ones get-values
 * priced (a Trade chart average needs MIN_CHARTS of them, the page's marketKeys() bar); the
 * bench weights are the engine's own readout, published by get-values as bench_share
 * (Jeremy's pick B, 2026-10-26). With no readout the fit is left unjudged rather than
 * approximated. Expected depth is not published, so it stays null: that only drops the depth
 * sentence from the reason and never moves the label.
 */
function fitContextFor(finder: Finder, data: ChartValuesResponse, shape: RosterShape): FitContext | null {
  const weights = benchWeightsFromReadout(data.bench_share);
  if (!weights) return null;
  const f = finder as unknown as FitFinder;
  const chartKeys = (f.CHART_KEYS || []).filter((k) => data.sources_included.includes(k));
  return buildFitContext(f, { shape, chartKeys, weights, expected: null, z: f.FIT_Z });
}

/** JEG-1115: one scored offer with the finder's fit label and reason (null when not judged). */
function withFit<T extends ScoredOffer>(
  o: T,
  finder: Finder,
  ctx: FitContext | null,
  mineRows: FinderRow[],
  theirRows: FinderRow[],
  rowByKey: Map<number, FinderRow>,
): T & { fit: string | null; fitReason: string | null; fitSides: FitSides | null } {
  if (!ctx) return { ...o, fit: null, fitReason: null, fitSides: null };
  const rows = (side: Array<{ player_key: number }>) =>
    side.map((p) => rowByKey.get(p.player_key)).filter((r): r is FinderRow => !!r) as unknown as FitRow[];
  const give = rows(o.userGives);
  const receive = rows(o.userGets);
  if (give.length !== o.userGives.length || receive.length !== o.userGets.length) return { ...o, fit: null, fitReason: null, fitSides: null };
  const fit = fitForTrade(finder as unknown as FitFinder, mineRows as unknown as FitRow[], theirRows as unknown as FitRow[],
    give, receive, ctx);
  return { ...o, fit: fit.fit, fitReason: fit.fit_reason, fitSides: fit.sides ?? null };
}

/** Minimal ViabilityRow from a trade candidate player summary. */
function toViabilityRow(p: { player_key: number; name: string; pos: string; value: number | null }): ViabilityRow {
  return { player_key: p.player_key, name: p.name, pos: p.pos, values: { ddf_value: p.value } };
}

// ---------- find_trades_league tool ----------

async function findTradesLeagueHandler(
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);

  let mineNames = playerNames(a.mine, "mine");
  const withLeague = hasLeagueInput(a) && a.opponents === undefined;
  if (!withLeague && !mineNames.length) throw new ToolInputError("mine is required: your roster's names (commas or new lines), or give league_paste or league_teams with my_team.");
  let opponents = withLeague ? [] : parseOpponents(a.opponents);
  if (!finderDeps?.finder) {
    throw new ToolUnavailableError("The trade finder is unavailable right now. Try again shortly.");
  }
  if (!finderDeps?.fetchCharts) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }

  const data = await finderDeps.fetchCharts(s.scoring, s.teams, s.superflex, s.league);
  const chartPlayers = chartPlayersOf(data);

  const league = withLeague ? leagueOf(a, chartPlayers, deps) : null;
  let myName = "My team";
  if (league) {
    const me = myTeamOf(league);
    myName = league.teams[me].name;
    if (!mineNames.length) mineNames = league.teams[me].players;
    opponents = league.teams.filter((_, i) => i !== me).map((t) => ({ name: t.name, roster: t.players.join("\n") }));
  }

  const mineRes = resolveNames(chartPlayers, mineNames);
  if (!mineRes.matched.length) throw new ToolInputError(emptyRoster("your roster", mineRes));
  const mineRows = mineRes.matched.map(toFinderRow);
  const mineKeys = new Set(mineRes.matched.map((p) => p.player_key));

  const shape = rosterShape(a, s.superflex, s.lineup);
  const vConfig = viabilityConfig(a);
  // Decision 4A (2026-11-21): acceptable trades only by default; viable_only=false keeps the full list.
  const viableOnly = parseBool(a.viable_only, "viable_only", true);
  const maxPerSide = parseBounded(a.max_per_side, "max_per_side", 2, 1, 4);
  const minRivalEdge = parseNonNegative(a.min_rival_edge, "min_rival_edge", 0);
  const limit = parseBounded(a.limit, "limit", 10, 1, 100);

  const allOffers: TradeOfferInput[] = [];
  const opponentsById = new Map<string, { name: string; index: number; rows: FinderRow[] }>();
  const allRowsByKey = new Map<number, FinderRow>();
  const perOpponent: Array<{
    name: string;
    opponent_index: number;
    tradesFound: number;
    unmatchedNames: string[];
    ambiguous?: Array<{ input: string; suggestions: string[] }>;
  }> = [];
  const nameSources: Array<{ res: ResolvedNames<PlayerValue>; team?: string }> = [{ res: mineRes }];
  // JEG-1329: every opponent's matched roster, in input order, for the site link (even teams with no trade).
  const leagueTeams: Array<{ name: string; keys: string[] }> = [];

  // Run each opponent pair sequentially (edge function memory).
  for (const [index, opp] of opponents.entries()) {
    const opponentId = String(index);
    const oppNames = splitNames(opp.roster);
    if (!oppNames.length) {
      leagueTeams.push({ name: opp.name, keys: [] });
      perOpponent.push({ name: opp.name, opponent_index: index, tradesFound: 0, unmatchedNames: [] });
      continue;
    }
    const oppRes = resolveNames(chartPlayers, oppNames);
    leagueTeams.push({ name: opp.name, keys: oppRes.matched.filter((p) => !mineKeys.has(p.player_key)).map((p) => String(p.player_key)) });
    nameSources.push({ res: oppRes, team: opp.name });
    const theirMatched = oppRes.matched.filter((p) => !mineKeys.has(p.player_key));
    if (!theirMatched.length) {
      perOpponent.push({ name: opp.name, opponent_index: index, tradesFound: 0, unmatchedNames: oppRes.unmatched, ...ambiguousOf(oppRes) });
      continue;
    }

    const theirRows = theirMatched.map(toFinderRow);
    const rowByKey = new Map<number, FinderRow>();
    for (const r of mineRows) rowByKey.set(r.player_key, r);
    for (const r of theirRows) rowByKey.set(r.player_key, r);
    opponentsById.set(opponentId, { name: opp.name, index, rows: theirRows });
    for (const [k, r] of rowByKey) allRowsByKey.set(k, r);

    const pairResult = findTradesForPair(finderDeps.finder, mineRows, theirRows, {
      maxSize: maxPerSide,
      minRivalEdge,
      // Never search a smaller pool than the previous per-opponent cap (50). A
      // higher limit asks for more so the shown list can still fill after dedupe.
      limit: Math.min(200, Math.max(50, limit)),
    });

    const pairOffers: TradeOfferInput[] = pairResult.trades.map((t) => ({
      team: opponentId,
      userGives: t.give.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
      userGets: t.receive.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
      userRoster: mineRows,
      theirRoster: theirRows,
    }));

    allOffers.push(...pairOffers);
    perOpponent.push({
      name: opp.name,
      opponent_index: index,
      tradesFound: pairResult.trades.length,
      unmatchedNames: oppRes.unmatched,
      ...ambiguousOf(oppRes),
    });
  }

  // Score, rank, and optionally filter.
  const ranked = scoreAndRankOffers(allOffers, shape, vConfig);
  const scored = viableOnly ? ranked.filter((o) => o.viable) : ranked;
  const nameNotes = [...(league?.notes ?? []), ...nameLines(nameSources, league)];

  // Package: best viable combination.
  const pkg = selectPackage(scored, mineRows, shape, vConfig.ddfKey);

  // JEG-1115: the fit label the finder shows, judged only for the trades returned.
  const finder = finderDeps.finder;
  const fitCtx = fitContextFor(finder, data, shape);
  const fitted = (o: ScoredOffer) => {
    const opponent = opponentsById.get(o.team)!;
    return { ...slimOffer(withFit({ ...o, team: opponent.name }, finder, fitCtx,
      mineRows, opponent.rows, allRowsByKey), true), opponent_index: opponent.index };
  };
  const shownTrades = scored.slice(0, limit).map(fitted);
  const viableCount = scored.filter((o) => o.viable).length;
  const packageOffers = pkg.offers.map(fitted);
  // Decision 4A: none passes every check, so the closest two across the league (ranked puts them first) and why.
  const closest = viableOnly && !viableCount ? ranked.slice(0, 2).map((o) => ({ ...fitted(o), why: failReasons(o) })) : [];
  const summary = tradeSummary(shownTrades, closest, viableCount, ranked.length, viableOnly, "the other team");

  // With no acceptable trade the closest rows are the ones the budget trims (at least one is kept).
  return boundedTrades<typeof closest[number] | typeof shownTrades[number]>(closest.length ? closest : shownTrades, "find_trades_league", limit, (rows, shortened) => {
    const shownTrades = closest.length ? [] : rows;
    const closestShown = (closest.length ? rows : []) as typeof closest;
    const lines: string[] = [
      ...header(data, s),
      ...nameNotes,
      "",
      `League scan: ${opponents.length} opponent${opponents.length === 1 ? "" : "s"}, ${ranked.length} candidate${ranked.length === 1 ? "" : "s"} (${viableCount} likely accepted), showing ${shownTrades.length}${shownTrades.length < limit && scored.length > shownTrades.length ? ` of limit ${limit}` : ""}.`,
      `Your roster: ${mineRes.matched.length} matched, ${missed(mineRes)}.`,
    ];
    if (shortened) lines.push("Fewer candidates shown to keep this reply compact; the selected package and full fit reasons are preserved.");
    lines.push("");
    const said = { force: false };

    if (packageOffers.length > 0) {
      lines.push(`Package (one trade per team, no player sent twice): ${packageOffers.length} trade${packageOffers.length === 1 ? "" : "s"}, your total gain +${pkg.totalDdfEdge.toFixed(1)}.`);
      lines.push(...tradeLines(packageOffers, (o) => o.team as string, said));
      lines.push("");
    }

    if (shownTrades.length) lines.push(viableOnly ? "Trades the other team would likely accept:" : "Candidates:");
    lines.push(...tradeLines(shownTrades, (o) => o.team as string, said));
    if (closestShown.length) {
      lines.push("Closest (each fails a check, so they would likely say no):");
      lines.push(...tradeLines(closestShown, (o) => o.team as string, said));
      lines.push("Set viable_only to false for every candidate.");
    }

    const structured = {
      as_of: data.as_of,
      setting: data.setting,
      package: {
        offers: packageOffers,
        totalDdfEdge: round1(pkg.totalDdfEdge),
        lineup: pkg.userLineupAfter.map((p) => ({ name: p.name, pos: p.pos, value: p.ddfValue })),
      },
      trades: shownTrades,
      total: ranked.length,
      shown: shownTrades.length,
      limit,
      viableCount,
      viable_only: viableOnly,
      ...(closestShown.length ? { closest: closestShown } : {}),
      perOpponent,
      mine: { matched: mineRes.matched.length, unmatched: mineRes.unmatched, ...ambiguousOf(mineRes) },
    };

    const work = {
      mine: mineNames.map((n: string) => workEntry(data.players, n)),
      ...leagueWork(league, data.players),
    };
    // JEG-1329: the site link opens the league finder with every team, yours first, not only yours.
    const teams = [{ name: myName, keys: mineRes.matched.map((p) => String(p.player_key)) }]
      .concat(leagueTeams);

    return finish(ok(lines.join("\n"), structured), {
      prepared, deps, settings: s, view: "finder", work, teams, summary,
    });
  });
}

const EXPLANATIONS: Record<string, string> = {
  methodology:
    "Values are 'value above waivers': how much more a player is expected to produce than a freely available replacement at the same position, in the user's league (scoring, team count, superflex). The headline value (DDF Value) is the average of the four published trade charts, each adjusted to the user's league (position and bench weighting); the projection sources are an alternate version. A stale or held source is left out of the average rather than counted as zero. Full method: the site's methodology pages.",
  sources:
    "Projection sources: ESPN, CBS rest-of-season, Razzball. Published trade charts: FantasyCalc, USA Today, FantasyPros, CBS. The get_values response lists which sources are included and excluded for the current week.",
  value_scale:
    "Value is points above a replacement-level player in that league. There is no fixed maximum: read values against each other, with the top of the list setting the scale. Players the league leaves on the waiver wire are worth about 0, and a value near 0 means replacement level in that league, not worthless. Always quote the value the tool returned.",
  scoring_formats:
    "standard = no points per reception, half_ppr = 0.5, ppr = 1.0. PPR lifts high-target receivers and pass-catching backs; standard favors rushers and touchdown-dependent players.",
  superflex:
    "Superflex adds a slot that takes a QB, which sharply raises QB values and shifts replacement levels. Charts that publish their own superflex values use them, in a superflex league and in a league that starts 2 QBs (a pasted DDF state or site link whose roster has 2 QB slots). The 2-QB league keeps its own starter and waiver counts, and with no superflex slot the QBs' share of the league's value comes from its own projections (points above its 2-QB replacement level), so QBs are usually worth more than in a superflex league.",
  tiers:
    "Tier is where a player sits in the league: starter (fills a starting lineup slot), bench (worth rostering as depth) or waiver (replacement level, freely available). It is not a quality band, so two players in the same tier can have very different values; compare values, not tiers.",
  how_to_trade:
    "1) Use compare_trade on both sides. 2) As a rough guide, a gap under about 2 points is roughly even and 5 or more is meaningful; this is a rule of thumb, not a measured threshold. 3) Use trade_targets to find similar-value partners. 4) Your own roster needs can outweigh the DDF Value sum. Values update weekly.",
};

function explain(topic: string): ToolResult {
  const text = EXPLANATIONS[topic];
  if (!text) throw new ToolInputError(`unknown topic: ${topic}. Must be one of: ${EXPLAIN_TOPICS.join(", ")}`);
  return ok(`Data Driven Football\n\n${text}`, { topic, text });
}

// ---------- state tools (JEG-1027) ----------

type Entry = { key?: string; name?: string };
const WORK_LISTS = ["give", "get", "mine", "theirs"];

interface ResolvedEntry {
  input: string;
  player: PlayerValue | null;
  note: string;
  /** The name match, kept so a miss can list its closest names without matching again; null for a key-only entry. */
  hit: NameMatch<PlayerValue> | null;
}

function resolveEntry(players: PlayerValue[], e: Entry): ResolvedEntry {
  const byKey = e.key !== undefined ? players.find((p) => String(p.player_key) === e.key) ?? null : null;
  if (byKey) return { input: e.name ?? e.key ?? "", player: byKey, note: "", hit: null };
  if (!e.name) return { input: e.key ?? "", player: null, note: `${e.key ?? ""}: NOT FOUND`, hit: null };
  const hit = matchName(players, e.name);
  return { input: e.name, player: hit.match === "ambiguous" ? null : hit.player, note: hit.note, hit };
}

/** JEG-1376: closest names are worked out for this many misspelled names at most; the rest are only named. */
const MAX_CLOSEST_MISSES = 5;

/**
 * JEG-1376: the "Could not match" entries for read_state. An ambiguous name lists every player it
 * fits, as compare_trade does; a misspelled name lists its closest names (for the first
 * MAX_CLOSEST_MISSES only, since each one scans every player); a key-only entry is only named.
 */
function missLabels(players: PlayerValue[], misses: ResolvedEntry[]): string[] {
  let scanned = 0;
  return misses.map((miss) => {
    if (!miss.hit) return miss.input;
    if (miss.hit.match === "ambiguous") return `${miss.input} (could be ${miss.hit.suggestions.map((p) => p.name).join(", ")})`;
    if (scanned >= MAX_CLOSEST_MISSES) return miss.input;
    scanned++;
    const near = closestNames(players, miss.input, miss.hit).map((p) => p.name);
    return near.length ? `${miss.input} (closest: ${near.join(", ")})` : miss.input;
  });
}

function inferView(work: Record<string, unknown>): string {
  if (work.give || work.get) return "compare";
  if (work.mine || work.theirs) return "finder";
  return "targets";
}

async function readState(args: Record<string, unknown>, fetchValues: FetchValues, deps?: Deps): Promise<ToolResult> {
  if (!deps?.codec) throw new ToolUnavailableError("The shared state reader is unavailable right now. Try again shortly.");
  if (!String(args.state ?? "").trim()) throw new ToolInputError("state is required: paste a ddf-state block or a site link");
  const prepared = prepare(args, deps);
  if (!prepared.state) {
    throw new ToolInputError("No usable DDF state found in the pasted text.");
  }
  const s = settings(prepared.args);
  const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
  const work = (prepared.state.work ?? {}) as Record<string, unknown>;

  const lists: Record<string, Array<{ input: string; player: PlayerValue | null; note: string }>> = {};
  const resolvedWork: Record<string, unknown> = {};
  const unmatched: string[] = [];
  const misses: ResolvedEntry[] = [];
  const lines: string[] = [...header(data, s), ""];
  for (const name of WORK_LISTS) {
    const list = work[name] as Entry[] | undefined;
    if (!list?.length) continue;
    const rows = list.map((e) => resolveEntry(data.players, e));
    lists[name] = rows.map(({ input, player, note }) => ({ input, player, note }));
    resolvedWork[name] = rows.map((r, i) => r.player ? { key: String(r.player.player_key), name: r.player.name } : list[i]);
    rows.filter((r) => !r.player).forEach((r) => { unmatched.push(r.input); misses.push(r); });
    // JEG-1124 (Jeremy 2026-10-30, "Letter A."): a name that matches no player gives no total.
    const missing = rows.filter((r) => !r.player).length;
    const total = Math.round(rows.reduce((t, r) => t + (r.player?.value ?? 0), 0) * 10) / 10;
    lines.push(missing
      ? `${name} (no total: ${missing} name${missing === 1 ? "" : "s"} not matched):`
      : `${name} (total ${total.toFixed(1)}):`);
    lines.push(...rows.map((r) => r.player ? `  ${r.player.name} (${r.player.pos}): ${r.player.value}` : `  ${r.note || `${r.input}: NOT FOUND`}`));
  }
  if (work.target) {
    const r = resolveEntry(data.players, work.target as Entry);
    lists.target = [{ input: r.input, player: r.player, note: r.note }];
    resolvedWork.target = r.player ? { key: String(r.player.player_key), name: r.player.name } : work.target;
    if (!r.player) { unmatched.push(r.input); misses.push(r); }
    lines.push(`target: ${r.player ? `${r.player.name} (${r.player.pos}): ${r.player.value}` : (r.note || `${r.input}: NOT FOUND`)}`);
  }
  if (!Object.keys(lists).length) lines.push("The state carries league settings only, no players.");
  // JEG-1376: name each unmatched player with its closest names, the way compare_trade does.
  if (misses.length) {
    lines.push("", `Could not match: ${missLabels(data.players, misses).join("; ")}. Ask the user which player they meant (or to check the spelling).`);
  }

  const view = typeof work.view === "string" ? work.view : inferView(work);
  const teamCount = Array.isArray(work.teams) ? work.teams.length : 0;
  const parts = [
    ...(teamCount ? [`${teamCount} teams${typeof work.my_team === "number" && (work.teams as Array<{ name?: string }>)[work.my_team] ? ` (yours: ${(work.teams as Array<{ name?: string }>)[work.my_team].name})` : ""}`] : []),
    ...Object.entries(lists).map(([k, rows]) => k === "target" ? `target ${rows[0].player?.name ?? rows[0].input}` : `${k} (${rows.length})`),
  ];
  const summary = `Read the state: ${parts.length ? parts.join(", ") : "league settings only"}` +
    `${unmatched.length ? `; ${unmatched.length} name${unmatched.length === 1 ? "" : "s"} not matched` : ""}.`;
  return finish(
    ok(lines.join("\n"), { as_of: data.as_of, setting: data.setting, lists, unmatched }),
    { prepared, deps, settings: s, view, work: resolvedWork, summary },
  );
}

async function makeState(args: Record<string, unknown>, fetchValues: FetchValues, deps?: Deps): Promise<ToolResult> {
  if (!deps?.codec) throw new ToolUnavailableError("The shared state writer is unavailable right now. Try again shortly.");
  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);
  const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
  const names = (v: unknown, field: string) => playerNames(v, field);
  const work: Record<string, unknown> = {};
  const unmatched: string[] = [];
  const toEntry = (input: string) => {
    const saved = savedKey(input);
    if (saved) return workEntry(data.players, input);
    const hit = matchName(data.players, input);
    if (hit.match === "ambiguous" || !hit.player) {
      if (!notEvaluated(input, data.players)) {
        unmatched.push(hit.match === "ambiguous" ? `${input} (${hit.suggestions.map((p) => p.name).join(" or ")})` : input);
      }
      return { name: input };
    }
    return { key: String(hit.player.player_key), name: hit.player.name };
  };
  // Connector walkthrough 2026-11-21: a league plus my_team is enough; your roster comes from your team.
  const league = hasLeagueInput(a) ? leagueOf(a, data.players, deps) : null;
  if (league) {
    work.teams = league.teams.map((t) => ({
      name: t.name.slice(0, 60),
      players: t.players.map((n, i) => (t.keys?.[i] ? { key: t.keys[i]!, name: n } : toEntry(n))),
    }));
    if (league.mine !== null) {
      work.my_team = league.mine;
      if (a.mine === undefined) work.mine = (work.teams as Array<{ players: unknown[] }>)[league.mine].players;
    }
  }
  for (const name of WORK_LISTS) {
    const list = names(a[name], name);
    if (list.length && !(name === "mine" && work.mine && league && a.mine === undefined)) work[name] = list.map(toEntry);
  }
  if (String(a.target ?? "").trim()) work.target = toEntry(checkName(String(a.target).trim(), "target"));
  if (!Object.keys(work).length && !prepared.state && !s.roster) {
    throw new ToolInputError("Give the league (league_paste or league_teams, with my_team), a roster (mine), a trade (give and get), a target, or a pasted state.");
  }
  const allViews = ["compare", "targets", "finder"];
  const view = allViews.includes(String(a.view)) ? String(a.view) : inferView({ ...(prepared.state?.work ?? {}), ...work });
  const saved: string[] = [];
  if (league) {
    saved.push(`${league.teams.length} teams${league.mine !== null ? `, yours is ${league.teams[league.mine].name}` : " (say which is the user's with my_team)"}`);
  }
  if (s.roster) saved.push("slots");
  const summary = `Saved${saved.length ? ` ${saved.join(" and ")}` : ""} with the league settings. Pass this state to later calls; it keeps the settings${s.roster ? ", slots" : ""}${league ? " and every roster" : ""}.`;
  const kd = league ? kdefLine(league.kickers ?? 0, league.defenses ?? 0) : "";
  const text = [
    ...header(data, s),
    ...(league?.notes ?? []),
    ...(kd ? [kd] : []),
    ...(league?.unsure?.length ? [`Could be more than one player: ${league.unsure.join("; ")}.`] : []),
    ...(unmatched.length ? [`Could not match: ${unmatched.join(", ")} (kept by name; the site will try again).`] : []),
  ].join("\n");
  return finish(ok(text, { as_of: data.as_of, setting: data.setting, unmatched, teams: league?.teams.map((t) => ({ name: t.name, players: t.players.length })) ?? [], my_team: league?.mine ?? null }), {
    prepared, deps, settings: s, view, work, block: true, summary,
  });
}
