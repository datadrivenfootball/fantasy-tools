// Sleeper: public API, no credentials (https://docs.sleeper.com). Read-only.
import { AppError, Fetch, getJSON } from "./errors.ts";
import { closestSize, DdfSettings, deriveRanks, int, LeagueSummary, Missing, num, pts, SUMMARY_VERSION, TeamSummary } from "./shape.ts";

const API = "https://api.sleeper.app/v1/";

// deno-lint-ignore no-explicit-any
type J = any;

export type PlayerNames = (ids: string[]) => Promise<Record<string, { n: string; p: string | null; t: string | null }>>;

export async function sleeperUser(f: Fetch, username: string) {
  const name = String(username || "").trim();
  if (!/^[A-Za-z0-9_]{2,30}$/.test(name)) {
    throw new AppError(400, "invalid_username", "Type your Sleeper username as it shows in the Sleeper app.");
  }
  const got = await getJSON(f, API + "user/" + encodeURIComponent(name), {}, "Sleeper");
  const u = got.body as J;
  if (!u || !u.user_id) throw new AppError(404, "sleeper_user_not_found", `We could not find a Sleeper user named ${name}.`);
  return { user_id: String(u.user_id), display_name: String(u.display_name || u.username || name) };
}

export async function sleeperSeason(f: Fetch): Promise<{ season: number; week: number | null }> {
  const st = (await getJSON(f, API + "state/nfl", {}, "Sleeper")).body as J;
  const season = int(st?.league_season ?? st?.season, 2000, 2100) ?? new Date().getUTCFullYear();
  return { season, week: int(st?.week, 0, 22) };
}

export async function sleeperLeagues(f: Fetch, userId: string) {
  const { season } = await sleeperSeason(f);
  const list = (await getJSON(f, `${API}user/${encodeURIComponent(userId)}/leagues/nfl/${season}`, {}, "Sleeper")).body as J;
  return {
    season,
    leagues: (Array.isArray(list) ? list : []).filter((l: J) => l && l.league_id).map((l: J) => ({
      league_key: String(l.league_id),
      name: String(l.name || "Sleeper league").slice(0, 80),
      season: Number(l.season) || season,
      teams: int(l.total_rosters),
      status: l.status ?? null,
    })),
  };
}

// app/next/sleeper-import.js settingsOf, server side (tests pin parity with the site's copy).
export function sleeperDdfSettings(lg: J): DdfSettings | null {
  if (!lg) return null;
  const pos: string[] = Array.isArray(lg.roster_positions) ? lg.roster_positions : [];
  const count = (list: string[]) => pos.filter((p) => list.includes(p)).length;
  const rec = lg.scoring_settings && Number(lg.scoring_settings.rec);
  const scoring = rec >= 1 ? "ppr" : rec >= 0.5 ? "half_ppr" : "standard";
  const roster: Record<string, number> = {
    QB: count(["QB"]), RB: count(["RB"]), WR: count(["WR"]), TE: count(["TE"]),
    FLEX: count(["FLEX", "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX", "RBTE_FLEX"]), BENCH: count(["BN"]),
  };
  for (const k of Object.keys(roster)) roster[k] = Math.min(20, roster[k]);
  roster.K = Math.min(3, count(["K"]));
  roster.DST = Math.min(3, count(["DEF"]));
  const sf = count(["SUPER_FLEX"]);
  const out: DdfSettings = { scoring, superflex: sf > 0 };
  if (sf >= 2) out.superflexSlots = 2;
  if (roster.QB >= 1) out.roster = roster as DdfSettings["roster"];
  const n = Number(lg.total_rosters);
  if (isFinite(n) && n >= 2) out.teams = closestSize(n);
  return out;
}

function sleeperFit(lg: J) {
  const fit: Record<string, unknown> = {};
  const n = Number(lg.total_rosters), te = Number(lg.scoring_settings?.bonus_rec_te);
  if (isFinite(n) && n >= 2 && ![8, 10, 12, 14].includes(n)) { fit.teams = n; fit.usedTeams = closestSize(n); }
  if (isFinite(te) && te > 0) fit.tePremium = te;
  return Object.keys(fit).length ? fit : null;
}

const WAIVER_TYPE: Record<number, string> = { 0: "rolling", 1: "reverse_standings", 2: "faab" };

export async function pullSleeper(f: Fetch, leagueId: string, sleeperUserId: string | null, names: PlayerNames, now = new Date()) {
  const id = String(leagueId);
  if (!/^\d{6,25}$/.test(id)) throw new AppError(400, "invalid_league", "That is not a Sleeper league ID.");
  const base = API + "league/" + id;
  const [lgR, usersR, rostersR, stateR] = await Promise.all([
    getJSON(f, base, {}, "Sleeper"),
    getJSON(f, base + "/users", {}, "Sleeper"),
    getJSON(f, base + "/rosters", {}, "Sleeper"),
    getJSON(f, API + "state/nfl", {}, "Sleeper"),
  ]);
  const lg = lgR.body as J, users = (usersR.body as J) || [], rosters = (rostersR.body as J) || [], state = stateR.body as J;
  if (!lg || !lg.league_id) throw new AppError(404, "league_not_found", "We could not find that Sleeper league.");
  const set = lg.settings || {};
  const miss = new Missing();
  const sources = ["sleeper:league", "sleeper:league/users", "sleeper:league/rosters", "sleeper:state/nfl"];

  const playoffStart = int(set.playoff_week_start, 2, 22);
  if (playoffStart === null) miss.add("settings.playoff_start_week", "Sleeper did not return a usable playoff_week_start");
  const lastRegular = playoffStart !== null ? playoffStart - 1 : null;
  const td = set.trade_deadline;
  const tradeDeadline = td === 99
    ? { week: null, date: null, none: true, source: "sleeper:league.settings.trade_deadline (99 = no deadline)" }
    : int(td, 1, 22) !== null
    ? { week: td, date: null, none: false, source: "sleeper:league.settings.trade_deadline" }
    : (miss.add("settings.trade_deadline", "Sleeper did not return a trade deadline week"), { week: null, date: null, none: false, source: null });
  const waiverType = WAIVER_TYPE[set.waiver_type as number] ?? null;
  if (waiverType === null) miss.add("settings.waiver_type", "Sleeper waiver_type is not 0, 1 or 2");
  const budget = waiverType === "faab" ? int(set.waiver_budget, 0, 100000) : null;

  const byUser: Record<string, J> = {};
  for (const u of users) if (u && u.user_id) byUser[u.user_id] = u;
  const sorted = [...rosters].sort((a: J, b: J) => (a.roster_id || 0) - (b.roster_id || 0));
  const allIds = sorted.flatMap((r: J) => [...(r.players || []), ...(r.reserve || []), ...(r.taxi || [])]).map(String);
  const nameMap = await names([...new Set(allIds)]);

  const teams: TeamSummary[] = sorted.map((r: J) => {
    const s = r.settings || {};
    const owner = byUser[r.owner_id];
    const managers = [r.owner_id, ...(r.co_owners || [])].filter(Boolean).map((uid: string) => ({
      id: String(uid),
      name: byUser[uid] ? String(byUser[uid].display_name || "") || null : null,
    }));
    const teamName = (owner?.metadata?.team_name && String(owner.metadata.team_name).trim()) ||
      (owner?.display_name ? String(owner.display_name) : `Team ${r.roster_id}`);
    const starters = new Set((r.starters || []).map(String));
    const reserve = new Set((r.reserve || []).map(String));
    const taxi = new Set((r.taxi || []).map(String));
    const startSlots = (lg.roster_positions || []).filter((p: string) => p !== "BN");
    const slotOf = (pid: string) => {
      if (reserve.has(pid)) return "IR";
      if (taxi.has(pid)) return "TAXI";
      const i = (r.starters || []).map(String).indexOf(pid);
      return i >= 0 && starters.has(pid) ? (startSlots[i] ?? "starter") : "BN";
    };
    const ids = [...new Set([...(r.players || []), ...(r.reserve || []), ...(r.taxi || [])].map(String))];
    const fpts = num(s.fpts), fa = num(s.fpts_against);
    return {
      team_key: String(r.roster_id),
      name: teamName.slice(0, 80),
      managers,
      standings: {
        wins: int(s.wins, 0, 99), losses: int(s.losses, 0, 99), ties: int(s.ties, 0, 99),
        points_for: fpts === null ? null : Math.round((fpts + (num(s.fpts_decimal) ?? 0) / 100) * 100) / 100,
        points_against: fa === null ? null : Math.round((fa + (num(s.fpts_against_decimal) ?? 0) / 100) * 100) / 100,
        rank: null, rank_source: null,
      },
      faab_remaining: budget !== null ? budget - (int(s.waiver_budget_used, 0, 100000) ?? 0) : null,
      waiver_priority: int(s.waiver_position, 1, 99),
      roster: ids.map((pid) => ({
        player_id: pid,
        name: nameMap[pid]?.n ?? null,
        position: nameMap[pid]?.p ?? null,
        nfl_team: nameMap[pid]?.t ?? null,
        slot: slotOf(pid),
        status: null,
      })),
    };
  });
  deriveRanks(teams, "derived: wins, then points for (Sleeper's default order)");
  if (!teams.length) miss.add("teams", "Sleeper returned no rosters");
  if (budget === null && waiverType === "faab") miss.add("settings.faab_budget", "Sleeper did not return waiver_budget");
  if (teams.length && teams.every((t) => t.waiver_priority === null)) miss.add("teams[].waiver_priority", "Sleeper returned no waiver_position");
  if (allIds.some((id) => !nameMap[id])) miss.add("teams[].roster[].name", "some Sleeper player ids are not in Sleeper's player list");

  // Schedule: every regular-season week (Sleeper has no projected team totals in matchups).
  const weeks = lastRegular ?? 14;
  const matchupRows = await Promise.all(
    Array.from({ length: weeks }, (_, i) => getJSON(f, `${base}/matchups/${i + 1}`, {}, "Sleeper").then((g) => g.body as J).catch(() => null)),
  );
  sources.push(`sleeper:league/matchups/1..${weeks}`);
  // Weeks after the current one are not played yet: Sleeper sends 0 there, which is not a score.
  const curWeek = int(state?.week, 0, 22);
  const played = (w: number) => curWeek === null || w <= curWeek;
  if (curWeek === null) miss.add("current_week", "Sleeper state/nfl returned no week, so future scores cannot be told from zeros");
  const schedule = matchupRows.map((rows, i) => {
    const groups: Record<string, J[]> = {};
    for (const m of Array.isArray(rows) ? rows : []) if (m && m.matchup_id != null) (groups[m.matchup_id] ||= []).push(m);
    return {
      week: i + 1,
      matchups: Object.values(groups).map((g) => ({
        team_keys: g.map((m) => String(m.roster_id)),
        points: g.map((m) => (played(i + 1) ? pts(m.points) : null)),
        projected_points: g.map(() => null),
        is_playoffs: false,
      })),
    };
  });
  if (matchupRows.some((r) => r === null)) miss.add("schedule", "some Sleeper matchup weeks did not load");

  const mine = sleeperUserId ? sorted.find((r: J) => String(r.owner_id) === sleeperUserId || (r.co_owners || []).map(String).includes(sleeperUserId)) : null;
  const summary: LeagueSummary = {
    shape: SUMMARY_VERSION,
    platform: "sleeper",
    league_key: id,
    season: Number(lg.season),
    name: String(lg.name || "Sleeper league").slice(0, 80),
    pulled_at: now.toISOString(),
    current_week: int(state?.week, 0, 22),
    settings: {
      num_teams: int(lg.total_rosters, 1, 64),
      ddf: sleeperDdfSettings(lg),
      fit: sleeperFit(lg),
      roster_positions: lg.roster_positions || [],
      scoring_raw: lg.scoring_settings ?? null,
      playoff_start_week: playoffStart,
      playoff_teams: int(set.playoff_teams, 1, 64),
      last_regular_week: lastRegular,
      trade_deadline: tradeDeadline,
      waiver_type: waiverType,
      faab_budget: budget,
    },
    teams,
    my_team_key: mine ? String(mine.roster_id) : null,
    schedule,
    missing: miss.rows,
    sources,
  };
  const raw = { league: lg, users, rosters, state, matchups: matchupRows };
  return { summary, raw };
}

// Sleeper asks clients to fetch /players/nfl at most once a day. Keep a slim copy.
export async function sleeperPlayerIndex(f: Fetch) {
  const got = await getJSON(f, API + "players/nfl", {}, "Sleeper");
  const all = (got.body || {}) as Record<string, J>;
  const slim: Record<string, { n: string; p: string | null; t: string | null }> = {};
  for (const [id, p] of Object.entries(all)) {
    const n = p?.full_name || [p?.first_name, p?.last_name].filter(Boolean).join(" ");
    if (n) slim[id] = { n: String(n), p: p.position ?? null, t: p.team ?? null };
  }
  return slim;
}
