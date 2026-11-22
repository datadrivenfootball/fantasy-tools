## 2026-11-18 - JEG-1696 kept league: change every setting, switch team, step back through setup

Contract: Jeremy (2026-11-17) wants a kept league to stay fully editable: back up through league setup, see and change
the selections, and "pretend I'm another team and see their options". Close every gap with the existing stores.

Gaps found (375px, pasted league and saved-only league):
1. setup.html ignored the saved league (localStorage ddf.v2.workspaces): a returning visitor saw "No rosters added yet"
   and could not change their team.
2. connect.html kept Next disabled for a saved-only league ("Paste your rosters to continue").
3. Entry trail: forward steps were plain text (connect: steps 2-3; setup: step 3) even with a league kept.
4. Completed entry steps were dark green on the dark green header (unreadable).
5. No way to switch team outside setup.html; the league menu had only Edit league / Start fresh, no settings link.
6. No marker when viewing as a team that is not yours.
7. Header overflowed 13px at 375px once the Bookmark button appeared (chip not re-fitted).

Changes: DDF.viewAs (site.js) reads/writes `me` plus `own` inside the existing records (ddf:pasted.own,
ws.ownTeamId, ddf:link.own); "Viewing as" picker in the league menu and at the start of the workspace step trail,
"✓ League settings" trail link, banner "Viewing as X. Not your team." with "Back to <yours>"; entry steps all links
when a league is kept; setup.html reads the saved league; connect Next accepts it; Bookmark render re-fits the chip.
Switching team drops ddf:moves (they were the other roster's waiver moves).

### Verified (check named)
- tests/test_league_view_as_render.py (new, 4 tests, 375px): saved-league setup + trail + contrast + connect Next;
  trail switch -> pasted me/own, moves dropped, team/waivers/build/values read the new team, banner, back; league
  menu switch on a saved league -> myTeamId/ownTeamId; setup still shows your own team; no overflow.
- Passed locally (RENDER_TESTS_REQUIRED=1): test_entry_pages, test_edit_league, test_bookmark_freshness,
  test_entry_sticky_bar, test_jeg1557_mobile_connect, test_team_engine_parity, test_sleeper_entry, test_league_card_pasted.
- test_entry_pages: one assertion changed on purpose (a cleared tab session now shows the saved league, not the
  empty state), per Jeremy 2026-11-17.
- test_render_sweep_coverage: 4 failures identical on origin/main (values_chart_fullscreen / compact_table unlisted).

### Claimed, not confirmed
- Chat-link leagues: own is kept in ddf:link.own; covered by code path only, no render test with a #s= league.
- Not checked in the in-app browser pane (all its tabs were in use by other sessions); headless Chromium at 375 instead.
