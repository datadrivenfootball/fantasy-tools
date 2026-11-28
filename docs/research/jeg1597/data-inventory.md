# JEG-1597 Data Inventory: Stat-Level Projections and Actuals

Authored by Claude Sonnet 4.6, 2026-11-09. Read-only research; no code or Supabase writes.

---

## Scoring Weights (from `pipelines/lib/scoring.py`)

The canonical weights used throughout the pipeline. Only skill players (QB/RB/WR/TE); K/DST use ESPN PPG rates directly.

| Stat                | PPR    | Half-PPR | Standard |
|---------------------|--------|----------|----------|
| passing_yards       | 0.04   | 0.04     | 0.04     |
| passing_tds         | 4.0    | 4.0      | 4.0      |
| interceptions       | −2.0   | −2.0     | −2.0     |
| rushing_yards       | 0.10   | 0.10     | 0.10     |
| rushing_tds         | 6.0    | 6.0      | 6.0      |
| **receptions**      | **1.0**| **0.5**  | **0.0**  |
| receiving_yards     | 0.10   | 0.10     | 0.10     |
| receiving_tds       | 6.0    | 6.0      | 6.0      |
| fumbles_lost        | −2.0   | −2.0     | −2.0     |

Format differences are entirely in `receptions`. TE premium is not currently a named format; it would add +0.5 per TE reception on top of PPR. Since `ppr − std = 1.0 × receptions`, receptions can always be reverse-engineered from the existing points totals for format rescoring.

---

## Dataset Tables

### A. Projection sources with per-stat breakdown (suitable for decomposition)

| Dataset | Path / Table | Source | Season / Weeks | Stat columns | Games field | Row count | Identity key | Join % to chart |
|---|---|---|---|---|---|---|---|---|
| ESPN ROS projections CSV | `data/inputs/espn_projections.csv` | ESPN scrape | 2026, single ROS snapshot (wk 2 vintage) | r_pass_yds, r_pass_tds, r_rush_yds, r_rush_tds, r_receptions, r_rec_yds, r_rec_tds (ROS totals) | espn_projected_games | 606 rows | player_norm only (no player_key in CSV) | ~52% by name |
| ESPN season projections | Supabase `espn_season_projections` | same | 2026 wk 2 (606 players), wk 3 (387 players) only | same 7 stat columns as CSV, as ROS totals | (none stored) | 993 | player_key | ~51% (593/1163) |
| CBS ROS projections | Supabase `cbs_ros_projections` | CBS scrape | 2026 wks 4–9 (daily snapshots) | raw_stats JSONB — QB: pass_att, pass_cmp, pass_yds, pass_td, int, rush_att, rush_yds, rush_td, fl; RB: rush_att, rush_yds, rush_td, tgt, rec, rec_yds, rec_td, fl; WR: same as RB + rush_att; TE: tgt, rec, rec_yds, rec_td, fl. All are ROS totals. | gp (rest-of-season games, reliable) | 12,091 (363–392 unique players/snapshot) | player_key | ~32% by count; covers starter tier |
| CBS ROS raw snapshot | `data/raw/sources/cbsros/<date>/snapshot.json` | same | 2026-09-30 only on disk | same as above | gp | 363 rows/file | player_norm | — |
| Razzball projections | Supabase `razzball_projections` | Razzball scrape | 2026 wks 4–9 (daily snapshots) | raw_stats JSONB — pg_pass_yds, pg_pass_td, pg_int, pg_rush_att, pg_rush_yds, pg_rush_td, pg_tgt, pg_rec, pg_rec_yds, pg_rec_td, pg_fum, pg_sacks, pg_snaps, pg_cmp, pg_att, share_rush, share_tgt. All per-game. | games_reported — **doubling quirk, unreliable. Use pg_* columns directly.** | 18,990 (560–691 unique players/snapshot) | player_key | ~44% by name (509/1163) |
| Razzball projections CSV | `data/inputs/razzball_projections.csv` | same | 2026, single ROS snapshot | same pg_* columns as above | games_reported (same quirk) | 513 rows | player_norm | ~44% by name |

### B. Projection sources with points totals only (not decomposable per-stat)

| Dataset | Path / Table | Source | Season / Weeks | Columns | Row count | Identity key | Join % to chart |
|---|---|---|---|---|---|---|---|
| ESPN weekly projections | `data/inputs/espn_weekly_projections_2026.csv` | ESPN bake | 2026 wks 1–9 | std, half_ppr, ppr totals per week | 4,637 | player_key | — |
| Sleeper weekly projections | `data/inputs/weekly_projections_sleeper.csv.gz` | Sleeper API | 2018–2026, all weeks | pts_std, pts_half_ppr, pts_ppr | 52,462 | sleeper_id + gsis_id | 66% via idmap (771/1163) |
| Source projection captures | Supabase `source_projection_captures` | ESPN, CBS, Razzball | 2026 wks 2–9 (ESPN), wks 3–9 (razzball), wks 4–9 (CBS) | points, ppg, games per player/source/week | 169,236 | player_key | — |
| data/history/week-*.json | `data/history/week-{2–9}.json` | Pipeline snapshots | 2026 wks 2–9 | ppg field: [std, half_ppr, ppr] triplets per player per source | — | internal id | — |

### C. Per-stat actuals (for backtest)

| Dataset | Path / Table | Season / Weeks | Stat columns | Row count | Identity key | Join % to chart | Notes |
|---|---|---|---|---|---|---|---|
| player_game_stats | Supabase `player_game_stats` | 2024–2026 wks 1–9 | stats JSONB: passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds, targets, receptions, receiving_yards, receiving_tds | 42,204 | players UUID → player_key (via players table) | ~1,518 player_keys for 2026 wks 1–4 | No fumbles_lost. Full coverage 2024–2025 and 2026 wks 1–4 (~1,000–1,100/wk). Weeks 5–8: 258–294 rows/wk (partial; source feed issue, not confirmed). Week 9: 36 rows (games in progress 2026-11-09). |

### D. Points-only actuals

| Dataset | Path / Table | Season / Weeks | Columns | Row count | Identity key | Join % to chart |
|---|---|---|---|---|---|---|
| Weekly actuals 2024–2026 | `data/inputs/weekly_actuals_2024_2026.csv` | 2024–2026 wks 1–9 | std, half_ppr, ppr | 14,656 | player_key | 67.5% (785/1163) |
| NFLverse actuals | `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz` | 2015–2025, all weeks | std, half_ppr, ppr | 61,977 | player_id (gsis_id) | 59.4% via idmap (691/1163) |
| NFLverse actuals (Supabase) | `nflverse_player_week_actuals` | 2015–2025 | actual_std, actual_half, actual_ppr | 61,977 | gsis_id (no player_key column) | — |

---

## Player Identity

| Key type | Source | Join mechanism | Match rate |
|---|---|---|---|
| player_key | Canonical; used in Supabase tables and most CSVs | Direct | Native |
| player_norm | ESPN/Razzball CSVs | `player_name_aliases` / `canonical_players.py` → player_key | ~95%+ for active players |
| sleeper_id | Sleeper CSV | `data/inputs/sleeper_projection_idmap.csv` sleeper_id → player_key | 902/1275 matched (71%) |
| gsis_id | Sleeper CSV, NFLverse | Same idmap gsis_id → player_key | 820 mapped |
| players UUID | Supabase `player_game_stats` | JOIN `players.id` → `players.player_key` | player_key present on 4,699/4,699 players |

**Chart player_keys**: `comparison-sources-data.json` top-level `player_keys` dict maps player_norm → player_key for all 1,163 chart players (week 9, PPR, 12-team). player_key is the right join key to all Supabase stat tables.

---

## Gaps

| Gap | Detail |
|---|---|
| ESPN stat lines missing for weeks 4–9 | Supabase `espn_season_projections` has only weeks 2–3 (upsert model, not append). The CSV is a single ROS snapshot. For week-9 stat lines, ESPN has no stored snapshot. |
| ESPN missing INT, fumbles, targets | The ESPN scraper does not capture interceptions, fumbles, or targets — only 7 stat columns (pass_yds/tds, rush_yds/tds, receptions, rec_yds/tds). |
| Razzball games field unreliable | `games_reported` has a known doubling quirk. Use pg_* per-game columns directly; do not compute ROS totals by multiplying by games_reported. |
| No per-stat actuals for 2015–2025 | The nflverse and actuals CSVs store scoring totals only. The Supabase `player_game_stats` goes back only to 2024. Per-stat lines for the 2015–2023 backtest do not exist in the repo. |
| player_game_stats wks 5–8 partial | Only 258–294 rows per week in 2026 weeks 5–8 vs ~1,100 for weeks 1–4. Likely a feed coverage issue; confirms weekly actuals CSV is the more complete 2026 actuals source. |
| NumberFire not populated | `numberfire_ros_projections` table: 0 rows. The pull script is present but no captures have been ingested. |
| CBSros player coverage (~360–392) | CBS ROS covers starter-tier players only; ~32–34% of the 1,163 chart players by player_key count. Missing long-tail bench players priced in the chart. |
| Format-rescoring for 2015–2025 backtest | Receptions can be reverse-engineered: `receptions = ppr − std`. TE premium (e.g. +0.5 per TE reception) = `ppr + 0.5×(ppr−std)` for TE. Fumbles cannot be recovered from points totals and are not in the nflverse CSV. |

---

## Recommendation: Which stat set to use per position, per use case

### Weeks 5–9 (current-season, forward-looking decomposition)

| Position | Recommended source | Rationale |
|---|---|---|
| QB | Razzball `razzball_projections` (Supabase, latest snapshot) | Most complete: includes pg_pass_yds, pg_pass_td, pg_int, pg_rush_yds, pg_rush_td, pg_fum. 577 players at week 9. |
| RB | Razzball (same) | Includes pg_rush_att, pg_rush_yds, pg_rush_td, pg_tgt, pg_rec, pg_rec_yds, pg_rec_td, share_rush. |
| WR/TE | Razzball (same) | Includes pg_tgt, pg_rec, pg_rec_yds, pg_rec_td. |
| Cross-check / fallback | CBS `cbs_ros_projections` (Supabase) | Smaller player set (~390/wk) but independent source. gp field is reliable. Use to validate Razzball per-game rates. |
| Games remaining | CBS `gp` for CBS rows; derive from `espn_projected_games` in ESPN CSV; for Razzball, infer from leaguewide schedule + bye data (`nfl_schedule_2024_2026.json`). Do NOT use Razzball `games_reported`. |

### 2015–2025 backtest

| Need | Recommended approach |
|---|---|
| Format rescoring (Std / Half / Full PPR) | Use `nflverse_player_week_actuals` or `weekly_actuals_nflverse_2015_2025.csv.gz`. Derive receptions = ppr − std. All format totals are computable. |
| TE premium scoring | `ppr + 0.5 × receptions` for TE, derivable from above. |
| Full stat-level decomposition (pass_yds, rush_att, etc.) | **Not available** for 2015–2023. Supabase `player_game_stats` covers 2024–2026 wks 1–4 completely. For 2015–2023, an external nflverse weekly player stats CSV (not currently in repo) would be required. |
| Identity join from nflverse to player_key | `sleeper_projection_idmap.csv`: gsis_id → player_key, matched for 820 players. 59.4% join rate to chart. For the full active set, the unmatched portion are pre-2024 players no longer in the identity map. |
