// Yahoo Fantasy Sports: OAuth 2.0 authorization code flow, read-only.
// Since 2026-07-22 Yahoo approves each app before its Fantasy API answers (JEG-1151);
// before approval every Fantasy call returns 403 and this module says so.
import { AppError, Fetch, getJSON } from "./errors.ts";
import { closestSize, DdfSettings, deriveRanks, int, LeagueSummary, Matchup, Missing, num, pts, settleWeek, SUMMARY_VERSION, TeamSummary } from "./shape.ts";

const AUTH = "https://api.login.yahoo.com/oauth2/request_auth";
const TOKEN = "https://api.login.yahoo.com/oauth2/get_token";
const API = "https://fantasysports.yahooapis.com/fantasy/v2";

// deno-lint-ignore no-explicit-any
type J = any;

export type YahooConfig = { clientId: string; clientSecret: string; redirectUri: string; scope: string };
export type YahooTokens = { access_token: string; refresh_token: string; expires_at: number; guid: string | null };

export function yahooConfig(env: (k: string) => string | undefined, functionsBase: string): YahooConfig | null {
  const clientId = env("YAHOO_CLIENT_ID"), clientSecret = env("YAHOO_CLIENT_SECRET");
  if (!clientId || !clientSecret) return null;
  return {
    clientId,
    clientSecret,
    redirectUri: env("YAHOO_REDIRECT_URI") || `${functionsBase}/ddf-account/yahoo/callback`,
    scope: env("YAHOO_SCOPE") ?? "",
  };
}

export function authorizeUrl(cfg: YahooConfig, state: string) {
  const u = new URL(AUTH);
  u.searchParams.set("client_id", cfg.clientId);
  u.searchParams.set("redirect_uri", cfg.redirectUri);
  u.searchParams.set("response_type", "code");
  u.searchParams.set("state", state);
  if (cfg.scope) u.searchParams.set("scope", cfg.scope);
  return u.toString();
}

async function tokenCall(f: Fetch, cfg: YahooConfig, form: Record<string, string>, now: number): Promise<YahooTokens> {
  let r: Response;
  try {
    r = await f(TOKEN, {
      method: "POST",
      headers: {
        authorization: "Basic " + btoa(`${cfg.clientId}:${cfg.clientSecret}`),
        "content-type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ redirect_uri: cfg.redirectUri, ...form }).toString(),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new AppError(502, "yahoo_unreachable", "We could not reach Yahoo sign-in just now. Try again.");
  }
  // The body may hold tokens or echo the code: read it, never log it.
  const body = await r.json().catch(() => null) as J;
  if (!r.ok || !body?.access_token) {
    const code = typeof body?.error === "string" ? body.error.replace(/[^a-z_]/gi, "").slice(0, 40) : "unknown";
    throw new AppError(502, "yahoo_token_failed", `Yahoo did not issue a token (${code}). Try connecting again.`);
  }
  return {
    access_token: body.access_token,
    refresh_token: body.refresh_token ?? form.refresh_token,
    expires_at: now + (Number(body.expires_in) || 3600) * 1000,
    guid: body.xoauth_yahoo_guid ? String(body.xoauth_yahoo_guid) : null,
  };
}

export const exchangeCode = (f: Fetch, cfg: YahooConfig, code: string, now = Date.now()) =>
  tokenCall(f, cfg, { grant_type: "authorization_code", code }, now);
export const refreshTokens = (f: Fetch, cfg: YahooConfig, t: YahooTokens, now = Date.now()) =>
  tokenCall(f, cfg, { grant_type: "refresh_token", refresh_token: t.refresh_token }, now).then((n) => ({ ...n, guid: n.guid ?? t.guid }));

async function yget(f: Fetch, token: string, path: string): Promise<J> {
  const got = await getJSON(f, `${API}${path}${path.includes("?") ? "&" : "?"}format=json`, { headers: { authorization: `Bearer ${token}` } }, "Yahoo");
  if (got.status === 403) {
    throw new AppError(403, "yahoo_app_not_approved", "Yahoo refused the Fantasy API call (403). Until Yahoo approves DDF's app for Fantasy API access, Yahoo leagues cannot be read.");
  }
  if (got.status === 401) throw new AppError(401, "yahoo_token_rejected", "Yahoo rejected the sign-in token. Disconnect Yahoo and connect it again.");
  if (got.status === 404 || !got.body) throw new AppError(404, "league_not_found", "Yahoo could not find that league.");
  return (got.body as J).fantasy_content;
}

// Yahoo JSON: arrays of single-key objects (and nested arrays) that together make one object.
export function ymerge(x: J): J {
  if (!Array.isArray(x)) return x && typeof x === "object" ? x : {};
  const out: J = {};
  for (const el of x) {
    if (Array.isArray(el)) Object.assign(out, ymerge(el));
    else if (el && typeof el === "object") Object.assign(out, el);
  }
  return out;
}
// Yahoo collections: {"0": {key: ...}, "1": {...}, "count": n}
export function yitems(coll: J, key: string): J[] {
  if (!coll || typeof coll !== "object") return [];
  const n = Number(coll.count);
  const keys = Object.keys(coll).filter((k) => /^\d+$/.test(k)).sort((a, b) => +a - +b);
  return (isFinite(n) ? keys.slice(0, n) : keys).map((k) => coll[k]?.[key]).filter((v) => v !== undefined);
}

export async function yahooLeagues(f: Fetch, token: string) {
  const fc = await yget(f, token, "/users;use_login=1/games;game_keys=nfl/leagues");
  const user = ymerge(yitems(fc.users, "user")[0]);
  const out: J[] = [];
  for (const g of yitems(user.games, "game")) {
    const game = ymerge(g);
    for (const l of yitems(game.leagues, "league")) {
      const lg = ymerge(l);
      out.push({ league_key: String(lg.league_key), name: String(lg.name || "Yahoo league").slice(0, 80), season: int(lg.season) ?? int(game.season), teams: int(lg.num_teams), status: lg.draft_status ?? null });
    }
  }
  return { leagues: out };
}

const REC_STAT_ID = "11"; // Yahoo NFL stat_id 11 = receptions

export function yahooDdfSettings(settings: J, numTeams: number | null): DdfSettings | null {
  if (!settings) return null;
  const pos = (settings.roster_positions || []).map((r: J) => r.roster_position).filter(Boolean);
  const count = (names: string[]) => pos.filter((p: J) => names.includes(p.position)).reduce((a: number, p: J) => a + (int(p.count, 0, 30) ?? 0), 0);
  const mods = (settings.stat_modifiers?.stats || []).map((s: J) => s.stat).filter(Boolean);
  const rec = Number(mods.find((s: J) => String(s.stat_id) === REC_STAT_ID)?.value ?? 0);
  const roster: Record<string, number> = {
    QB: count(["QB"]), RB: count(["RB"]), WR: count(["WR"]), TE: count(["TE"]),
    FLEX: count(["W/R/T", "W/R", "W/T", "R/T"]), BENCH: count(["BN"]),
  };
  for (const k of Object.keys(roster)) roster[k] = Math.min(20, roster[k]);
  roster.K = Math.min(3, count(["K"]));
  roster.DST = Math.min(3, count(["DEF"]));
  const sf = count(["Q/W/R/T"]);
  const out: DdfSettings = { scoring: rec >= 1 ? "ppr" : rec >= 0.5 ? "half_ppr" : "standard", superflex: sf > 0 };
  if (sf >= 2) out.superflexSlots = 2;
  if (roster.QB >= 1) out.roster = roster as DdfSettings["roster"];
  if (numTeams !== null && numTeams >= 2) out.teams = closestSize(numTeams);
  return out;
}

const YAHOO_STATUS: Record<string, Matchup["status"]> = { preevent: "not_started", midevent: "live", postevent: "final" };
const WAIVER: Record<string, string> = { R: "rolling", FR: "reverse_standings", continual: "continual" };

export async function pullYahoo(f: Fetch, token: string, leagueKey: string, now = new Date()) {
  if (!/^\d+\.l\.\d+$/.test(leagueKey)) throw new AppError(400, "invalid_league", "That is not a Yahoo league key (like 470.l.848938).");
  const lk = encodeURIComponent(leagueKey);
  const [setFc, stFc, roFc] = await Promise.all([
    yget(f, token, `/league/${lk}/settings`),
    yget(f, token, `/league/${lk}/standings`),
    yget(f, token, `/league/${lk}/teams/roster`),
  ]);
  const meta = ymerge(setFc.league[0]);
  const settings = ymerge(ymerge(setFc.league[1]).settings);
  const miss = new Missing();
  const numTeams = int(meta.num_teams, 1, 64);
  const usesFaab = String(settings.uses_faab) === "1";
  const playoffStart = int(settings.playoff_start_week, 1, 22);
  const endWeek = int(meta.end_week, 1, 22);
  const tradeEnd = typeof settings.trade_end_date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(settings.trade_end_date) ? settings.trade_end_date : null;
  if (!tradeEnd) miss.add("settings.trade_deadline", "Yahoo returned no trade_end_date");
  if (usesFaab) miss.add("settings.faab_budget", "Yahoo's API gives each team's faab_balance but not the league's starting budget");

  const rosterByTeam: Record<string, J> = {};
  for (const t of yitems(ymerge(roFc.league[1]).teams, "team")) {
    const team = ymerge(t);
    rosterByTeam[team.team_key] = team.roster;
  }
  let myKey: string | null = null;
  const teams: TeamSummary[] = yitems(ymerge(stFc.league[1]).standings?.[0]?.teams ?? ymerge(ymerge(stFc.league[1]).standings).teams, "team").map((t: J) => {
    const team = ymerge(t);
    if (String(team.is_owned_by_current_login) === "1") myKey = String(team.team_key);
    const st = team.team_standings || {};
    const ot = st.outcome_totals || {};
    const roster = rosterByTeam[team.team_key];
    const players = yitems(roster?.["0"]?.players ?? ymerge(roster).players, "player").map((p: J) => {
      const pl = ymerge(p);
      const sel = ymerge(pl.selected_position);
      return {
        player_id: String(pl.player_key),
        name: pl.name?.full ?? null,
        position: pl.display_position ?? pl.primary_position ?? null,
        nfl_team: pl.editorial_team_abbr ? String(pl.editorial_team_abbr).toUpperCase() : null,
        slot: sel.position ?? null,
        status: pl.status ?? null,
      };
    });
    return {
      team_key: String(team.team_key),
      name: String(team.name || team.team_key).slice(0, 80),
      managers: (team.managers || []).map((m: J) => m.manager).filter(Boolean).map((m: J) => ({ id: String(m.guid || m.manager_id), name: m.nickname ?? null })),
      standings: {
        wins: int(ot.wins, 0, 99), losses: int(ot.losses, 0, 99), ties: int(ot.ties, 0, 99),
        points_for: pts(st.points_for), points_against: pts(st.points_against),
        rank: int(st.rank, 1, 64), rank_source: int(st.rank, 1, 64) !== null ? "yahoo:team_standings.rank" : null,
      },
      faab_remaining: usesFaab ? int(team.faab_balance, 0, 100000) : null,
      waiver_priority: int(team.waiver_priority, 1, 64),
      roster: players,
    };
  });
  deriveRanks(teams, "derived: wins, then points for (Yahoo returned no rank)");

  // Schedule with Yahoo's own team projections: one scoreboard call per week.
  const lastWeek = endWeek ?? 17;
  const weeks = Array.from({ length: lastWeek - (int(meta.start_week, 1, 22) ?? 1) + 1 }, (_, i) => (int(meta.start_week, 1, 22) ?? 1) + i);
  const schedule: LeagueSummary["schedule"] = [];
  const curWeek = int(meta.current_week, 0, 22);
  const rawBoards: J[] = [];
  for (let i = 0; i < weeks.length; i += 4) {
    const batch = await Promise.all(weeks.slice(i, i + 4).map((w) => yget(f, token, `/league/${lk}/scoreboard;week=${w}`).catch(() => null)));
    batch.forEach((fc, j) => {
      rawBoards.push(fc);
      const sb = fc ? ymerge(ymerge(fc.league[1]).scoreboard) : null;
      const given: (Matchup["status"] | null)[] = [];
      const matchups: Matchup[] = yitems(sb?.["0"]?.matchups ?? sb?.matchups, "matchup").map((m: J) => {
        const sides = yitems(m?.["0"]?.teams ?? m?.teams, "team").map(ymerge);
        given.push(YAHOO_STATUS[String(m.status)] ?? null);
        return {
          team_keys: sides.map((s: J) => String(s.team_key)),
          points: sides.map((s: J) => pts(s.team_points?.total)),
          projected_points: sides.map((s: J) => pts(s.team_projected_points?.total)),
          is_playoffs: String(m.is_playoffs) === "1",
          status: "live" as const,
        };
      });
      // Yahoo's matchup status (preevent / midevent / postevent) decides; 0.00 before kickoff is not a score.
      settleWeek(weeks[i + j], curWeek, matchups, given);
      schedule.push({ week: weeks[i + j], matchups });
    });
  }
  if (curWeek === null) miss.add("current_week", "Yahoo returned no current_week; scores rely on each matchup's status");
  if (rawBoards.some((b) => b === null)) miss.add("schedule", "some Yahoo scoreboard weeks did not load");

  // Probe (JEG-1732): does Yahoo expose per-player weekly projections? Recorded, never fatal.
  const probes = await probeProjections(f, token, lk, teams, int(meta.current_week, 1, 22));

  const summary: LeagueSummary = {
    shape: SUMMARY_VERSION,
    platform: "yahoo",
    league_key: leagueKey,
    season: int(meta.season) ?? now.getUTCFullYear(),
    name: String(meta.name || leagueKey).slice(0, 80),
    pulled_at: now.toISOString(),
    current_week: int(meta.current_week, 0, 22),
    settings: {
      num_teams: numTeams,
      ddf: yahooDdfSettings(settings, numTeams),
      fit: null,
      roster_positions: (settings.roster_positions || []).flatMap((r: J) => Array(int(r.roster_position?.count, 0, 30) ?? 0).fill(r.roster_position?.position)),
      scoring_raw: { stat_categories: settings.stat_categories ?? null, stat_modifiers: settings.stat_modifiers ?? null },
      playoff_start_week: playoffStart,
      playoff_teams: int(settings.num_playoff_teams, 1, 64),
      last_regular_week: playoffStart !== null ? playoffStart - 1 : null,
      trade_deadline: { week: null, date: tradeEnd, none: false, source: tradeEnd ? "yahoo:settings.trade_end_date" : null },
      waiver_type: usesFaab ? "faab" : (WAIVER[String(settings.waiver_type)] ?? null),
      faab_budget: null,
    },
    teams,
    my_team_key: myKey,
    schedule,
    probes,
    missing: miss.rows,
    sources: ["yahoo:league/settings", "yahoo:league/standings", "yahoo:league/teams/roster", `yahoo:league/scoreboard;week=${weeks[0]}..${lastWeek}`],
  };
  return { summary, raw: { settings: setFc, standings: stFc, rosters: roFc, scoreboards: rawBoards } };
}

async function probeProjections(f: Fetch, token: string, lk: string, teams: TeamSummary[], week: number | null) {
  const keys = teams.flatMap((t) => t.roster.map((p) => p.player_id)).slice(0, 3);
  if (!keys.length || week === null) return { player_projection_probe: "skipped: no players or no current week" };
  const out: Record<string, unknown> = { week, player_keys: keys };
  for (const [label, type] of [["actual_week", "week"], ["projected_week", "projected_week"]] as const) {
    try {
      const fc = await yget(f, token, `/league/${lk}/players;player_keys=${keys.join(",")}/stats;type=${type};week=${week}`);
      const text = JSON.stringify(fc);
      out[label] = { ok: true, has_player_points: text.includes("player_points"), mentions_projected: /projected/i.test(text), sample: text.slice(0, 600) };
    } catch (e) {
      out[label] = { ok: false, error: e instanceof AppError ? e.code : "error" };
    }
  }
  return out;
}
