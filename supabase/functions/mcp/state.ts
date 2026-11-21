// JEG-1027: DDF state in and out of the MCP tools (spec: docs/design/llm-site-state.md).
// The codec itself is app/v2/ddf-state.js, loaded from the published site at cold start (index.ts),
// so the page and the tools read and write one format. Pure functions, no Deno APIs.

// deno-lint-ignore no-explicit-any
export type State = Record<string, any>;

export interface Codec {
  normalize(input: unknown): { state: State | null; warnings: string[] };
  encodeQuery(state: State): string;
  decodeBlock(text: string): { state: State | null; warnings: string[] };
  encodeBlock(state: State, opts?: { url?: string }): string;
}

export interface Deps {
  codec: Codec | null;
  siteOrigin: string;
  /** The site's league paste reader (next/league-paste.js), for league_paste; null when it could not be loaded. */
  paste?: import("./league.ts").PasteReader | null;
}

export const ROUTES: Record<string, string> = {
  compare: "#compare-trade",
  targets: "#trade-targets",
  finder: "#find-trade",
  // JEG-1329: the league finder, opened from its own share link (workspace.js shareHash).
  league: "#find-league",
  risers: "#risers-fallers",
  // JEG-1029: audit_values opens the Values auditing tab (its Health check sub-tab by default).
  audit: "#values-auditing",
};

// JEG-1031: get-values prices the whole league, so a state's settings beyond scoring, teams and superflex
// (roster shape, shares, bso, inj, conf, weeks) go to it as `league`. SUPERFLEX stays a top-level
// input so an explicit tool argument still wins over the pasted state.
export function leagueExtras(league: State | null | undefined): State | null {
  if (!league) return null;
  const out: State = {};
  for (const key of ["shares", "bso", "inj", "conf", "weeks"]) if (league[key] !== undefined) out[key] = league[key];
  const roster: State = {};
  for (const [k, v] of Object.entries(league.roster ?? {})) if (k !== "SUPERFLEX" && v !== undefined) roster[k] = v;
  if (Object.keys(roster).length) out.roster = roster;
  return Object.keys(out).length ? out : null;
}

export interface Prepared {
  args: Record<string, unknown>;
  state: State | null;
  warnings: string[];
}

// Merge a pasted state (block, bare JSON or site link) into the tool arguments. Explicit arguments win.
export function prepare(args: Record<string, unknown>, deps?: Deps): Prepared {
  const warnings: string[] = [];
  let state: State | null = null;
  if (typeof args.state === "string" && args.state.trim()) {
    if (!deps?.codec) {
      warnings.push("The shared state reader is unavailable right now, so the pasted state was not read; using the other settings.");
    } else {
      const r = deps.codec.decodeBlock(args.state);
      state = r.state;
      // The codec's "no DDF state found" line repeats the sentence added below.
      warnings.push(...r.warnings.filter((w) => !/no ddf state found/i.test(w)));
      if (!state) warnings.push("No usable DDF state was found in the pasted text; using the other settings.");
    }
  }
  const merged: Record<string, unknown> = { ...args };
  delete merged.state;
  // An older connector tool list sent the settings as one object: read it the same as top-level fields.
  const given = args.settings;
  if (given && typeof given === "object" && !Array.isArray(given)) {
    for (const k of ["scoring", "teams", "superflex", "slots"]) {
      const v = (given as Record<string, unknown>)[k];
      if (merged[k] === undefined && v !== undefined) merged[k] = v;
    }
  }
  delete merged.settings;
  const league = state?.league;
  if (league) {
    if (merged.scoring === undefined) merged.scoring = league.scoring;
    if (merged.teams === undefined && league.teams) merged.teams = league.teams;
    // A saved league is the whole league: a roster with no SUPERFLEX slot has none.
    if (merged.superflex === undefined && merged.slots === undefined) {
      merged.superflex = Number(league.roster?.SUPERFLEX ?? 0) > 0;
    }
    const extras = leagueExtras(league);
    if (extras) merged.league = extras;
  }
  // Connector walkthrough 2026-11-21: the rosters a state carries stand in for the roster fields, so later calls
  // need only the state. A player saved with a key is passed as #key; the tools read it back by key.
  const work = state?.work;
  if (work) {
    const names = (list: unknown) => Array.isArray(list)
      ? list.map((p: State) => (p?.key !== undefined ? `#${p.key}` : String(p?.name ?? ""))).filter(Boolean).join("\n")
      : undefined;
    const pasted = merged.league_paste !== undefined || merged.league_teams !== undefined;
    if (!pasted && Array.isArray(work.teams) && work.teams.length) {
      merged.league_teams = work.teams.map((t: State) => ({ name: t.name, players: names(t.players) ?? "" }));
      if (merged.my_team === undefined && work.my_team !== undefined) merged.my_team = work.my_team;
    }
    for (const k of ["mine", "theirs"]) if (merged[k] === undefined && work[k]?.length && !pasted) merged[k] = names(work[k]);
  }
  return { args: merged, state, warnings };
}

export interface Finish {
  prepared: Prepared;
  deps?: Deps;
  settings: { scoring: string; teams: number; superflex: number; roster?: Record<string, number> | null; notes?: string[] };
  view: string;
  work?: State;
  bare?: boolean;   // a plain site link with no state (explain)
  block?: boolean;  // append the pasteable block (make_state)
  /** JEG-1329: a league scan's teams (yours first). The link opens the league finder with all of them. */
  teams?: LeagueTeam[];
  /**
   * Connector walkthrough 2026-11-21 (part B, "clear, short answers"): one plain line that answers the question. It
   * opens the text and is the first key of structuredContent (hosts show the JSON).
   */
  summary?: string;
}

export interface LeagueTeam {
  name: string;
  keys: string[];
}

// JEG-1329: the league finder's share text, as app/v2/workspace.js encodeShare writes it:
// name:key,key|name:key. A numeric key is base 36, any other key is ~ and percent-encoded.
// The site reads it with decodeShare; tests/node/connector_both_sides_check.mjs pins the round trip.
export function leagueShareText(teams: LeagueTeam[]): string {
  const key = (k: string) => (/^\d+$/.test(k) ? Number(k).toString(36) : `~${encodeURIComponent(k)}`);
  return teams.map((t) => `${encodeURIComponent(t.name)}:${t.keys.map(key).join(",")}`).join("|");
}

// Add the site link, the state to continue on the site, and any notes to a tool result.
export function finish<R extends { content: Array<{ type: "text"; text: string }>; structuredContent?: Record<string, unknown> }>(
  result: R,
  f: Finish,
): R {
  const { prepared, deps, settings: s } = f;
  const notes = [...new Set([...(s.notes ?? []), ...prepared.warnings])];

  const league: State = { ...(prepared.state?.league ?? {}), scoring: s.scoring, teams: s.teams };
  // Slots given in this call are saved with the league, so later calls need not resend them.
  if (s.roster) league.roster = { ...(league.roster ?? {}), ...s.roster };
  // The link must describe the league actually priced. An explicit superflex argument
  // can override SF1 or SF0 in a pasted state, so replace that slot in either case.
  if (s.superflex || league.roster?.SUPERFLEX !== undefined) {
    league.roster = { ...(league.roster ?? {}), SUPERFLEX: s.superflex ? 1 : 0 };
  }
  const work: State = { ...(prepared.state?.work ?? {}), ...(f.work ?? {}), view: f.view };
  // Every league roster rides along by key only (a name only for a player with no key), so a 12-team league
  // stays about a kilobyte in each reply; the site and the tools read players back by key.
  if (Array.isArray(work.teams)) {
    work.teams = work.teams.map((t: State) => ({
      name: t.name,
      players: (t.players ?? []).map((p: State) => (p?.key !== undefined ? { key: p.key } : p)),
    }));
  }
  const state: State = { v: 1, league, work };

  const route = ROUTES[f.view] ?? ROUTES.targets;
  let url = `${deps?.siteOrigin ?? ""}/${route}`;
  let outState: State | null = state;
  if (f.bare) {
    url = `${deps?.siteOrigin ?? ""}/`;
    outState = null;
  } else if (deps?.codec) {
    const norm = deps.codec.normalize(state);
    outState = norm.state;
    if (outState) url = `${deps.siteOrigin}/${route}?${deps.codec.encodeQuery(outState)}`;
  }
  if (!f.bare && f.teams?.length) {
    // The league finder's own link: every team, team 0 marked as yours (wm=0), then the league
    // settings in the page's link parameters (the codec's league part, no work lists).
    const settingsQuery = deps?.codec && outState?.league ? deps.codec.encodeQuery({ v: 1, league: outState.league }) : "";
    url = `${deps?.siteOrigin ?? ""}/${ROUTES.league}?workspace=${leagueShareText(f.teams)}&wm=0${settingsQuery ? `&${settingsQuery}` : ""}`;
  }

  const block = f.block && deps?.codec && outState ? deps.codec.encodeBlock(outState, { url }) : "";
  const summary = f.summary?.trim() || "";
  const text = (summary ? `${summary}\n` : "") + result.content[0].text +
    (notes.length ? `\n\n${notes.join("\n")}` : "") +
    (block ? `\n\n${block}` : deps ? `\n\nOpen this on the site: ${url}` : "");
  return {
    ...result,
    content: [{ type: "text", text }],
    structuredContent: { ...(summary ? { summary } : {}), ...(result.structuredContent ?? {}), site_url: deps ? url : null, state: outState, notes },
  };
}
