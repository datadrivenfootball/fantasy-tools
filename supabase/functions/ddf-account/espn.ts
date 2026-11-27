// ESPN: public leagues by league ID, no cookies (private leagues need the later
// browser-extension step). Read-only.
import { AppError, Fetch, getJSON } from "./errors.ts";
import { closestSize, DdfSettings, int, LeagueSummary, Missing, num, pts, settleWeek, SUMMARY_VERSION, TeamSummary } from "./shape.ts";

const API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/";

// deno-lint-ignore no-explicit-any
type J = any;

// Mirrors app/next/espn-import.js.
const PRO_TEAM: Record<number, string> = {
  1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC",
  13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT",
  24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
};
const POS: Record<number, string> = { 1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF" };
const SLOT = { QB: 0, RB: 2, RBWR: 3, WR: 4, WRTE: 5, TE: 6, OP: 7, DST: 16, K: 17, BENCH: 20, IR: 21, FLEX: 23 };
const SLOT_NAME: Record<number, string> = {
  0: "QB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE", 6: "TE", 7: "OP", 16: "D/ST", 17: "K", 20: "BN", 21: "IR", 23: "FLEX",
};
const REC_STAT = 53;

export function espnSeasonNow(now = new Date()) {
  return now.getUTCMonth() < 2 ? now.getUTCFullYear() - 1 : now.getUTCFullYear();
}

export function parseEspnLeagueId(text: string): { id: string; season: number | null } | null {
  const t = String(text || "").trim();
  const season = /[?&]seasonId=(\d{4})\b/i.exec(t);
  const m = /[?&]leagueId=(\d{1,12})\b/i.exec(t) || /^(\d{4,12})$/.exec(t.replace(/[?#].*$/, "").replace(/\/+$/, ""));
  return m ? { id: m[1], season: season ? Number(season[1]) : null } : null;
}

function recPoints(lg: J) {
  const items = lg?.settings?.scoringSettings?.scoringItems;
  const item = (Array.isArray(items) ? items : []).find((s: J) => s && s.statId === REC_STAT);
  return item ? { points: Number(item.points) || 0, te: item.pointsOverrides && Number(item.pointsOverrides[SLOT.TE]) } : { points: 0, te: NaN };
}

// app/next/espn-import.js settingsOf, server side (tests pin parity with the site's copy).
export function espnDdfSettings(lg: J): DdfSettings | null {
  if (!lg || !lg.settings) return null;
  const c = lg.settings.rosterSettings?.lineupSlotCounts;
  const counts = c && typeof c === "object" ? c : null;
  const n = (k: keyof typeof SLOT) => {
    const v = Number((counts || {})[SLOT[k]]);
    return isFinite(v) && v > 0 ? Math.floor(v) : 0;
  };
  const rec = recPoints(lg).points;
  const out: DdfSettings = { scoring: rec >= 1 ? "ppr" : rec >= 0.5 ? "half_ppr" : "standard", superflex: false };
  const roster: Record<string, number> = { QB: n("QB"), RB: n("RB"), WR: n("WR"), TE: n("TE"), FLEX: n("FLEX") + n("RBWR") + n("WRTE"), BENCH: n("BENCH") };
  for (const k of Object.keys(roster)) roster[k] = Math.min(20, roster[k]);
  roster.K = Math.min(3, n("K"));
  roster.DST = Math.min(3, n("DST"));
  const sf = n("OP");
  out.superflex = sf > 0;
  if (sf >= 2) out.superflexSlots = 2;
  if (counts && roster.QB >= 1) out.roster = roster as DdfSettings["roster"];
  const size = Number(lg.settings.size);
  if (isFinite(size) && size >= 2) out.teams = closestSize(size);
  return out;
}

const VIEWS = ["mSettings", "mTeam", "mRoster", "mMatchup", "mStatus"];

// ESPN's own session cookies for a private league. The browser extension will send these;
// on staging they can be pasted once from a computer. Stored sealed, like Yahoo tokens.
export type EspnSession = { espn_s2: string; swid: string };

export function validEspnSession(x: { espn_s2?: unknown; swid?: unknown }): EspnSession {
  const s2 = String(x.espn_s2 ?? "").trim().replace(/^espn_s2=/, "");
  let swid = String(x.swid ?? "").trim().replace(/^SWID=/i, "");
  if (/^[0-9A-F-]{36}$/i.test(swid)) swid = `{${swid}}`;
  if (!/^[A-Za-z0-9%+/=._-]{60,2000}$/.test(s2)) throw new AppError(400, "bad_espn_s2", "That espn_s2 value doesn't look right. Copy the whole value of the espn_s2 cookie.");
  if (!/^\{[0-9A-F-]{36}\}$/i.test(swid)) throw new AppError(400, "bad_swid", "That SWID doesn't look right. It looks like {1A2B3C4D-....}, with the curly brackets.");
  return { espn_s2: s2, swid: swid.toUpperCase() };
}

export async function readEspnLeague(f: Fetch, id: string, season: number, session?: EspnSession) {
  const url = `${API}${season}/segments/0/leagues/${encodeURIComponent(id)}?${VIEWS.map((v) => "view=" + v).join("&")}`;
  const headers: Record<string, string> = { accept: "application/json" };
  if (session) headers.cookie = `espn_s2=${session.espn_s2}; SWID=${session.swid}`;
  const got = await getJSON(f, url, { headers }, "ESPN");
  if (got.status === 401 || got.status === 403) {
    throw session
      ? new AppError(403, "espn_session_rejected", "ESPN refused those session keys for this league. Sign in to ESPN on a computer, copy espn_s2 and SWID again, and make sure you are in this league.")
      : new AppError(403, "espn_private", "This ESPN league is private: ESPN shows it only to members who are signed in. Add your ESPN session keys below (on a computer), or wait for the DDF browser extension.");
  }
  if (got.status === 404 || !got.body) throw new AppError(404, "league_not_found", `We could not find ESPN league ${id} for ${season}.`);
  return got.body as J;
}

export function summarizeEspn(lg: J, id: string, season: number, now = new Date()) {
  const s = lg.settings || {};
  const miss = new Missing();
  const members: Record<string, J> = {};
  for (const m of lg.members || []) if (m?.id) members[m.id] = m;
  const memberName = (mid: string) => {
    const m = members[mid];
    return m ? (m.displayName || [m.firstName, m.lastName].filter(Boolean).join(" ") || null) : null;
  };
  const acq = s.acquisitionSettings || {};
  const usesBudget = acq.isUsingAcquisitionBudget === true;
  const budget = usesBudget ? int(acq.acquisitionBudget, 0, 100000) : null;
  const sched = s.scheduleSettings || {};
  const regularWeeks = int(sched.matchupPeriodCount, 1, 22);
  if (regularWeeks === null) miss.add("settings.last_regular_week", "ESPN did not return matchupPeriodCount");
  const deadlineMs = num(s.tradeSettings?.deadlineDate);
  const tradeDeadline = deadlineMs && deadlineMs > 0
    ? { week: null, date: new Date(deadlineMs).toISOString(), none: false, source: "espn:settings.tradeSettings.deadlineDate" }
    : (miss.add("settings.trade_deadline", "ESPN returned no trade deadline date"), { week: null, date: null, none: false, source: null });

  const teams: TeamSummary[] = (lg.teams || []).map((t: J) => {
    const rec = t.record?.overall || {};
    const name = t.name || [t.location, t.nickname].filter(Boolean).join(" ") || t.abbrev || `Team ${t.id}`;
    return {
      team_key: String(t.id),
      name: String(name).slice(0, 80),
      managers: (t.owners || []).map((o: string) => ({ id: String(o), name: memberName(o) })),
      standings: {
        wins: int(rec.wins, 0, 99), losses: int(rec.losses, 0, 99), ties: int(rec.ties, 0, 99),
        points_for: pts(rec.pointsFor), points_against: pts(rec.pointsAgainst),
        rank: int(t.playoffSeed, 1, 64) ?? int(t.rankCalculatedFinal, 1, 64),
        rank_source: t.playoffSeed ? "espn:teams.playoffSeed" : t.rankCalculatedFinal ? "espn:teams.rankCalculatedFinal" : null,
      },
      // a missing spent amount is unknown, not 0
      faab_remaining: budget !== null && int(t.transactionCounter?.acquisitionBudgetSpent, 0, 100000) !== null
        ? budget - int(t.transactionCounter?.acquisitionBudgetSpent, 0, 100000)! : null,
      waiver_priority: int(t.waiverRank, 1, 64),
      roster: (t.roster?.entries || []).map((e: J) => {
        const p = e.playerPoolEntry?.player || {};
        return {
          player_id: String(e.playerId),
          name: p.fullName ?? null,
          position: POS[p.defaultPositionId] ?? null,
          nfl_team: PRO_TEAM[p.proTeamId] ?? null,
          slot: SLOT_NAME[e.lineupSlotId] ?? String(e.lineupSlotId),
          status: p.injuryStatus ?? null,
        };
      }),
    };
  });
  if (!teams.length) miss.add("teams", "ESPN returned no teams");
  if (budget !== null && teams.some((t) => t.faab_remaining === null)) miss.add("teams[].faab_remaining", "ESPN returned no acquisitionBudgetSpent for some teams");
  if (teams.length && teams.every((t) => t.waiver_priority === null)) miss.add("teams[].waiver_priority", "ESPN returned no waiverRank");

  // Matchups after the current one are not played yet: ESPN sends 0 there, which is not a score.
  const curWeek = int(lg.status?.currentMatchupPeriod, 0, 30);
  const byWeek: Record<number, LeagueSummary["schedule"][number]> = {};
  for (const m of lg.schedule || []) {
    const wk = int(m.matchupPeriodId, 1, 30);
    if (wk === null) continue;
    const sides = [m.home, m.away].filter(Boolean);
    (byWeek[wk] ||= { week: wk, matchups: [] }).matchups.push({
      team_keys: sides.map((x: J) => String(x.teamId)),
      points: sides.map((x: J) => pts(x.totalPoints)),
      projected_points: sides.map((x: J) => pts(x.totalProjectedPointsLive)),
      is_playoffs: Boolean(m.playoffTierType && m.playoffTierType !== "NONE"),
      status: "live",
    });
  }
  for (const w of Object.values(byWeek)) settleWeek(w.week, curWeek, w.matchups);
  if (curWeek === null) miss.add("current_week", "ESPN returned no currentMatchupPeriod; unplayed weeks are told apart only by all-zero scores");
  const pos = s.rosterSettings?.lineupSlotCounts || {};
  const summary: LeagueSummary = {
    shape: SUMMARY_VERSION,
    platform: "espn",
    league_key: id,
    season,
    name: String(s.name || `ESPN league ${id}`).slice(0, 80),
    pulled_at: now.toISOString(),
    current_week: int(lg.status?.currentMatchupPeriod, 0, 30),
    settings: {
      num_teams: int(s.size, 1, 64),
      ddf: espnDdfSettings(lg),
      fit: null,
      roster_positions: Object.entries(pos).flatMap(([k, v]) => Array(Math.max(0, Number(v) || 0)).fill(SLOT_NAME[Number(k)] ?? `slot${k}`)),
      scoring_raw: s.scoringSettings ?? null,
      playoff_start_week: regularWeeks !== null ? regularWeeks + 1 : null,
      playoff_teams: int(sched.playoffTeamCount, 1, 64),
      last_regular_week: regularWeeks,
      trade_deadline: tradeDeadline,
      waiver_type: usesBudget ? "faab" : miss.add("settings.waiver_type", "ESPN non-FAAB waiver order type is not read yet; waiverRank per team is"),
      faab_budget: budget,
    },
    teams,
    my_team_key: null,
    schedule: Object.values(byWeek).sort((a, b) => a.week - b.week),
    missing: miss.rows,
    sources: VIEWS.map((v) => "espn:view=" + v),
  };
  return summary;
}
