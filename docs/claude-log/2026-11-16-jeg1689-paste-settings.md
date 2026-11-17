## 2026-11-16 - JEG-1689: a pasted league sets the league settings it shows

Contract: a pasted whole-league rosters page sets the team count and the lineup it evidences (starting slots, FLEX,
SUPERFLEX, K, DEF, bench) on the engine, keeps rostered player counts, and League settings marks each read value
"From your paste" until the reader confirms or changes it. No value formula changed.

Before: after a paste only the QB flex count reached the engine (JEG-1571 `qbFlexSlots`); team count and every other
roster slot stayed at the engine's current values (site default 12 teams, 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K /
1 DEF / 7 bench). The whole-league reader drops per-player slots (`extractPlayers` sets `slot: ""`), so the lineup is
read from the slot-label lines in each team's block (`league-paste.js blocks`).

Rules (`league-paste.js inferSettings`, durable reference):
- Team count = teams read, unless the paste looks cut off (a team with no players or fewer than half the biggest
  roster: why `partial`) or the count is not 8/10/12/14 (`curve-widget.js setTeams`; why `unsupported`, no rounding).
- Lineup only from whole rosters: every team shows a bench label and at least one slot label per player read. A slot
  count is used only when every team shows the same count and the engine runs it (QB..FLEX 1-5, SUPERFLEX 0-2, K/DEF
  0-3, bench 0-14). No K or DEF label anywhere: K and DEF are not read. "SF" is never a slot (San Francisco's code).
- Bench = largest bench shown, raised to the biggest roster (not on IR) minus the starting slots.
- A partial paste reads no lineup. W/R, W/T and RB/WR flex labels count as FLEX (the engine has one RB/WR/TE flex).
- `ddf:pasted.pasteSettings` keeps what was read; `ddf:pasted.confirmed` what the reader confirmed (saved) on
  settings.html. A confirmed field is never set from the paste again; the same league read again keeps it.

### Verified (check named)
- `node tests/test_paste_settings.js` (22): ESPN 10-team, Yahoo 12-team superflex, Sleeper 14-team fixtures
  (`tests/fixtures/paste_defaults`, built by `make.js`) read every value; partial paste reads nothing and says so;
  before/after on the live reader's fixtures (5 teams: bench 7 -> 5, team count kept, Sleeper DEF not read) and on the
  real Yahoo pastes (no change); confirmed fields; notice copy for each case.
- `node tests/test_entry_league_paste.js` (32): record-shape assertion now lists `pasteSettings` (the shape changed by
  this ticket); `node tests/test_v2_league_paste.js` (12).
- `python3.12 -m unittest tests.test_jeg1689_paste_settings_render` (4, Chromium on built dist/): engine runs 10 teams
  and 6 bench after the ESPN paste; every read value marked; a change clears its marker; saving records confirmations;
  the same paste read again keeps them; another league is read fresh; partial paste changes nothing; no paste, no
  notice; 390 and 1440 wide no overflow.
- Existing render tests still pass: test_jeg1646_optional_roster, test_jeg1632_kdef_slots, test_jeg1571_qb_flex,
  test_entry_sticky_bar (others in the PR body).

### Claimed, not confirmed
- Real full-league pastes from each site (not trimmed) read the same as the shape fixtures; the fixtures follow the
  page shapes in tests/fixtures/league_paste, not fresh copies.
- The pages have one (light) theme; a dark color scheme renders the same light page (checked the notice color only).
- Follow-up seen, not fixed here: the reader matches kicker "Jake Bates" to TE "John Bates" and also lists him as a
  kicker (one line, two entries); inferSettings counts that line once.
