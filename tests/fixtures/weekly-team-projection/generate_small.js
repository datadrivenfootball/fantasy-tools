// Generator for small.json (fake ids and teams only). Run: node tests/fixtures/weekly-team-projection/generate_small.js > tests/fixtures/weekly-team-projection/small.json
const AS = "2026-11-16T13:30:00Z", ASE = "2026-11-16T12:40:00Z";
const cell = v => ({value: v, source: "manual:entry", as_of: AS, reason: null});
const miss = r => ({value: null, source: null, as_of: null, reason: r});
const team = (id, name) => ({id, name, record: cell({w: 6, l: 5, t: 0}), points_for: cell(1200), points_against: cell(1150), division: miss("the league has no divisions")});
const state = {version: "league-state/1", league: {id: "fake-league-1", provider: "sleeper", capture: "manual", season: 2026}, captured_at: AS,
  my_team_id: "1", teams: [team("1", "Team One"), team("2", "Team Two")], record_through_week: cell(11),
  schedule: cell([{week: 12, median_game: false, games: [{home: "1", away: "2"}]}, {week: 13, median_game: false, games: [{home: "2", away: "1"}]}, {week: 14, median_game: false, games: [{home: "1", away: "2"}]}]),
  playoff_rules: {spots: cell(2), start_week: cell(15), last_regular_week: cell(14), byes: cell(0), seeding_rule: cell("record"), tiebreak: miss("not entered")},
  trade_deadline_week: cell("none")};
// [id, pos, sleeperTeam, half-PPR points per week]
const players = [
  ["fk-qa1", "QB", "AAA", 20], ["fk-qa2", "QB", "BBB", 15], ["fk-ra1", "RB", "AAA", 14], ["fk-ra2", "RB", "CCC", 12],
  ["fk-ra3", "RB", "DDD", 9], ["fk-wa1", "WR", "LAR", 16], ["fk-wa2", "WR", "BBB", 11], ["fk-wa3", "WR", "CCC", 8],
  ["fk-ta1", "TE", "DDD", 7], ["fk-ta2", "TE", "AAA", 10],
  ["fk-qb1", "QB", "CCC", 18], ["fk-qb2", "QB", "DDD", 13], ["fk-rb1", "RB", "BBB", 10], ["fk-rb2", "RB", "AAA", 6],
  ["fk-wr1", "WR", "CCC", 12], ["fk-wr2", "WR", "BBB", 9], ["fk-wr3", "WR", "AAA", 5], ["fk-te1", "TE", "CCC", 6]];
// nflverse codes: LA is the Rams (Sleeper LAR). DDD on bye week 12, LA on bye week 13.
const schedule = [
  [12, "AAA", "BBB"], [12, "CCC", "LA"], [12, "EEE", "FFF"],
  [13, "AAA", "CCC"], [13, "BBB", "DDD"], [13, "EEE", "FFF"],
  [14, "AAA", "DDD"], [14, "BBB", "LA"], [14, "CCC", "EEE"]].map(([week, home_team, away_team], i) => ({game_id: "2026_" + week + "_" + i, game_type: "REG", week, home_team, away_team}));
const byeOf = {12: ["DDD"], 13: ["LA"], 14: []};
const code = t => t === "LAR" ? "LA" : t;
const rows = [];
const pts = (source, x) => ({points_std: x - 1, points_half_ppr: x, points_ppr: x + 1, scoring_basis: source === "sleeper" ? "sleeper:pts_* as given (RotoWire)" : "espn:stat line rescored with v_player_game_actuals"});
const keyOf = id => 900000 + players.findIndex(p => p[0] === id);
[12, 13, 14].forEach(w => players.forEach(([id, pos, t, x]) => {
  const bye = byeOf[w].includes(code(t));
  // Sleeper: no row for a bye week (as Sleeper gives it); fk-wa3 has no week 14 row (the missing week)
  if (!bye && !(id === "fk-wa3" && w === 14)) rows.push(Object.assign({source: "sleeper", as_of: AS, season: 2026, content_week: 12, target_week: w, source_player_id: id, sleeper_id: id, player_key: keyOf(id), position: pos, team: t, opponent: null, stats: {rec_yd: x * 10}}, pts("sleeper", x)));
  // ESPN cross-check: weeks 12-13 only, 1 point lower, and a 0 row for a bye (MR-20)
  if (w <= 13) rows.push(Object.assign({source: "espn", as_of: ASE, season: 2026, content_week: 12, target_week: w, source_player_id: "e" + id, sleeper_id: /^fk-.a/.test(id) ? null : id, player_key: keyOf(id), position: pos, team: code(t), opponent: null, stats: null}, bye ? {points_std: 0, points_half_ppr: 0, points_ppr: 0, scoring_basis: "espn:stat line rescored with v_player_game_actuals"} : pts("espn", x - 1)));
}));
rows.push(Object.assign({source: "espn", as_of: ASE, season: 2026, content_week: 12, target_week: 12, source_player_id: "e-unresolved", sleeper_id: null, player_key: null, position: "WR", team: "EEE", opponent: null, stats: null}, pts("espn", 30)));
const out = {
  _about: "JEG-1658 fixture: fake league, fake player ids and fake team codes (LA/LAR alias kept on purpose). Rows have the warehouse source_weekly_projections columns used by the module.",
  state,
  slots: ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "BN", "BN", "BN", "BN", "K", "DEF"],
  scoring: "half_ppr",
  rosters: {"1": ["fk-qa1", "fk-qa2", "fk-ra1", "fk-ra2", "fk-ra3", "fk-wa1", "fk-wa2", "fk-wa3", "fk-ta1", "fk-ta2", "fk-k1"],
            "2": ["fk-qb1", "fk-qb2", "fk-rb1", "fk-rb2", "fk-wr1", "fk-wr2", "fk-wr3", "fk-te1", "KC"]},
  players: {"fk-k1": ["Fake Kicker", "K", "AAA"], "KC": ["KC", "DEF", "KC"]},
  schedule,
  injuries: [
    {sleeper_id: "fk-ta2", status: "IR", week: 11, return_week: 13, source: "manual:expected return"},
    {sleeper_id: "fk-qb1", status: "Out", week: 12, source: "nflverse_injury_snapshots"},
    {sleeper_id: "fk-wr2", status: "Questionable", week: 12, source: "nflverse_injury_snapshots"}],
  projections: rows
};
process.stdout.write(JSON.stringify(out, null, 1) + "\n");
