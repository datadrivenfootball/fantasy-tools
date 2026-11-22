## 2026-11-22 - Injury flags in the connector's trade answers

Contract: Jeremy, 2026-11-22: "connector injury flags: YES, follow-up PR (get-values reads the daily status file;
find_trades, find_trades_league, compare_trade, trade_targets show a short injury flag; flag only, no label/rule/value
change, connector deploy needs Jeremy's separate approval so do not deploy)."

- get-values reads the site's `v2/player-status.js` (optional; no copy, no flags) and adds `injury: {status, label,
  level, body?}` to a flagged player and `injury_source: {source, as_of, shown, note}` to the answer, under the site's
  rules (`get-values/injury.ts`: the Waivers freshness and id/team/position match, the site's severity map).
- The MCP tools print " [Out, hamstring]" after a flagged name and one line per answer or trade: "Injury flag: X is Out
  (hamstring). A flag, not a stopper: the trade may not work as planned." Structured results carry `injury` on the
  player. Healthy players print as before.
- The trade reply budget (JEG-1123) does not measure the flags, as it already leaves out the site link and the state:
  measured with them, half the players flagged cut find_trades_league from 5 trades shown to 2.
- Not deployed. Deploy of get-values and mcp waits for Jeremy's approval.

### Verified (check named)
- `tests.test_injury_flag_connector` (tests/node/injury_flag_connector_check.mjs): severity and flag parity with
  app/next/injury-flag.js + app/v2/waivers.js on 12 rows x 4 copies (fresh, stale, future, undated); get-values with
  every other priced player flagged answers identically to no status copy once `injury`/`injury_source` are removed
  (plain and include=charts), a stale copy flags nobody; find_trades_league (USO 10-29, Team 3), find_trades (Team 9),
  compare_trade and trade_targets identical structured and text answers apart from the tags and flag lines, 59 tags.
- Before the budget change the same check failed (find_trades_league shown 2 vs 5).
- Existing: test_mcp_remote, test_connector_roundtrip, test_get_values_value_context, test_mcp_week,
  test_connector_inventory, test_connector_analyses, test_league_mapping, test_jeg1365_two_qb_superflex_values,
  mcp_answer_format_check, mcp_entry_check, connector_both_sides_check. `deno check` on mcp/index.ts reports the same
  4 errors as main (none new); get-values/index.ts checks clean.

### Claimed, not confirmed
- Live answers after a deploy (not deployed).
