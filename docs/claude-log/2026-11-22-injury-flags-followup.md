## 2026-11-22 - Injury flags follow-up: page weight, visible flag text, Buy / Sell

Contract: independent review of #1518 / #1519 and Jeremy's decision of 2026-11-22 ("Buy/Sell injury chips: YES, small
follow-up using the shared function"). Display only, as before.

- (a) `pipelines/pull_player_status.py` writes `injury_body_part` only when there is one. On the 2026-11-22 live pull
  the published status script is 47,977 bytes with no body part, 69,897 with a null on every record (+46%), 52,809 now
  (+10%).
- (b) `statusFreshness` / `statusOf` moved from `app/v2/waivers.js` to `app/v2/player-status-rule.js`
  (`window.DDFStatusRule`, 3.5 KB, 1.6 KB gzipped); waivers.js requires and re-exports them. Build a Trade and Values load
  the rule file instead of waivers.js (76.6 KB, 22.4 KB gzipped). find, team, waivers and the v2 shell load it before
  waivers.js. The waivers mutation harnesses (`tests/test_waivers_status.py`, `tests/test_waivers_math.py`) copy and
  mutate the rule file where the moved code now lives: the harness target moved, the rules did not.
- (c) The Why line now says it in text: "Injury flag: X is Out (hamstring). A flag, not a stopper: the trade may not
  work as planned." (phones show no tooltip).
- (d) Buy / Sell: chip beside the name in both lists, the swap options and the value table; the row's aria-label ends
  "Injury: Out, hamstring."; the swap shows the Why line.

### Verified (check named)
- `tests.test_injury_flag` (rule file shared with Waivers, Build and Values do not load waivers.js, new Why text),
  `tests.test_injury_flag_render` (new `test_buy_sell_flags_change_no_list`: both lists in full identical with half
  the listed players flagged; chips, aria-labels, the swap's Why line, 375 and 1440, no overflow; Find and Build tests
  with the new text), `tests.test_daily_player_status` (body part absent, not null; assertion changed by that review).
- Locally, with the rule move: test_waivers_mutation_specificity, test_waivers_render, test_waivers_status,
  test_waivers_math, test_waivers_views, test_player_flags, test_build_v2_page, test_build_root_pages,
  test_build_lineup_card_render, test_build_pin_selected_render, test_find_natural_fit2_render, test_ddf_why,
  test_find_engine_parity, test_values_page_engine_parity, test_validate_shards (115 tests, OK).

### Claimed, not confirmed
- Not ours, reported only: on main, Build's roster picker at 320px wraps player names every few letters.
