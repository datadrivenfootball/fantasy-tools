// Draft tool daily pull (JEG-1667, Phase 0): pure parsers shared by the
// edge function (index.ts, Deno) and the local runner (tools/draft_pull.mjs,
// Node). No network, no database. Every row carries the season the source
// itself states; a page for another season fails closed.

export const SEASON = 2026;

// FantasyPros draft cheat sheets (public HTML; robots.txt allows /nfl/rankings/,
// Crawl-delay 5). The full consensus is embedded as `var ecrData = {...}`.
export const FP_ECR_PAGES = {
  STD: "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
  HALF: "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php",
  PPR: "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php",
};
export const FP_CRAWL_DELAY_MS = 6000;

// ESPN's public player list for the season (the same call its draft room
// makes; no sign-in): published auction values, average auction value and ADP.
export const ESPN_URL = (season) =>
  `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${season}/segments/0/leaguedefaults/3?view=kona_player_info`;
export const ESPN_FILTER = JSON.stringify({
  players: { limit: 600, sortDraftRanks: { sortPriority: 100, sortAsc: true, value: "PPR" } },
});

// The JSON object that starts at text[start], matched brace by brace
// (strings and escapes respected).
export function balancedObject(text, start) {
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < text.length; i += 1) {
    const c = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === "{") depth += 1;
    else if (c === "}" && --depth === 0) return text.slice(start, i + 1);
  }
  throw new Error("unbalanced JSON object");
}

const num = (v) => {
  const n = Number(v);
  return v === null || v === undefined || v === "" || !isFinite(n) ? null : n;
};

// -> {season, scoring, sourceUpdatedAt, rows}. Throws on a missing table, a
// season other than `season`, a scoring other than `scoring`, or under 150 rows.
export function parseFpEcr(html, scoring, season = SEASON) {
  const m = /ecrData\s*=\s*/.exec(html);
  if (!m) throw new Error("fantasypros: ecrData not found");
  const d = JSON.parse(balancedObject(html, m.index + m[0].length));
  if (Number(d.year) !== season) throw new Error(`fantasypros: page season ${d.year}, expected ${season}`);
  if (d.ranking_type_name !== "draft") throw new Error(`fantasypros: ranking type ${d.ranking_type_name}`);
  if (d.scoring !== scoring) throw new Error(`fantasypros: scoring ${d.scoring}, expected ${scoring}`);
  const rows = (d.players || []).map((p) => ({
    source: "fantasypros_ecr",
    season,
    scoring,
    source_player_id: String(p.player_id),
    player_name: p.player_name,
    pos: p.player_position_id === "DST" ? "DST" : p.player_position_id,
    team: p.player_team_id || null,
    bye: num(p.player_bye_week),
    rank_overall: num(p.rank_ecr),
    rank_pos: p.pos_rank || null,
    tier: num(p.tier),
    rank_sd: num(p.rank_std),
    dollars: null,
    aav: null,
    adp: null,
  }));
  if (rows.length < 150) throw new Error(`fantasypros: only ${rows.length} players`);
  return {
    season,
    scoring,
    sourceUpdatedAt: d.last_updated_ts ? new Date(Number(d.last_updated_ts) * 1000).toISOString() : null,
    rows,
  };
}

const ESPN_POS = { 1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST" };
const ESPN_TEAMS = {
  1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN",
  11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
  21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR", 30: "JAX",
  33: "BAL", 34: "HOU",
};

// -> {season, rows}: one row per player per ESPN format (STD, PPR). dollars =
// ESPN's published auction value (the platform price); aav = average price
// paid in ESPN auctions; adp = average draft position.
export function parseEspn(doc, season = SEASON) {
  const players = (doc && doc.players) || [];
  const rows = [];
  players.forEach((r) => {
    const p = r.player || {};
    const pos = ESPN_POS[p.defaultPositionId];
    if (!pos) return;
    const ranks = p.draftRanksByRankType || {};
    const own = p.ownership || {};
    [["STD", "STANDARD"], ["PPR", "PPR"]].forEach(([scoring, key]) => {
      const rk = ranks[key];
      if (!rk) return;
      rows.push({
        source: "espn",
        season,
        scoring,
        source_player_id: String(p.id),
        player_name: p.fullName,
        pos,
        team: ESPN_TEAMS[p.proTeamId] || null,
        bye: null,
        rank_overall: num(rk.rank),
        rank_pos: null,
        tier: null,
        rank_sd: null,
        dollars: num(rk.auctionValue),
        aav: num(own.auctionValueAverage),
        adp: num(own.averageDraftPosition),
      });
    });
  });
  if (rows.length < 300) throw new Error(`espn: only ${rows.length} rows`);
  return { season, rows };
}
