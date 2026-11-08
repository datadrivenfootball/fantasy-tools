## 2026-11-08 - JEG-1570 Sleeper: load rosters from the league link or ID

Contract (Jeremy, 2026-11-07): Sleeper rosters are public, so a Sleeper league link or ID should load every roster with
no copy and paste and no further asks; simplify the screen when Sleeper is selected. This reverses JEG-1131's "no
platform fetch" for Sleeper only (ESPN and Yahoo unchanged).

Feasibility, checked from a real browser on the datadrivenfootball.github.io origin (Playwright, live fetch):
- api.sleeper.app/v1 answers cross-origin reads (state, user, league, users, rosters): no key, no sign-in.
- A missing ID returns 404 with body `null`. A last-season ID returns the league with `season` "2025" and status
  complete. Sleeper has no private leagues in the read API: any league ID is readable.
- A public 12-team league (a company account's, not stored here) loaded in about 180 ms over 3 parallel calls. 344
  players matched; 1 id was not in our identity table.
- Rate limits: Sleeper asks apps to stay under about 1000 calls a minute. One load is 4 calls (state, league, users,
  rosters), plus the site's own sleeper-players.json, and the same ID is not loaded twice in a row.

What changed
- `app/next/sleeper-import.js` (new): `parseId` reads sleeper.com and sleeper.app links, bare IDs and links with query
  strings.
  - `load` fetches the four endpoints and names every team (team name, else display name; duplicates get "(2)";
    ownerless rosters become "Team N").
  - Each roster becomes the lines a rosters page shows ("Name POS TEAM"), read by the same matcher as a paste
    (`DDF.leaguePaste.fromBlocks`, one team at a time, so emoji names and names that differ only by punctuation keep
    their own rosters). The result is the same shape and the same players as the paste path.
    Defenses show as not evaluated; ids we cannot name show as not found.
  - League name and ID come from the league; the ID stays on the device. Settings (scoring from `rec`, team count when
    8/10/12/14, lineup slots, superflex) are read from the league.
  - Errors have plain-word messages: invalid, not found, old season, no rosters yet, network.
- `pipelines/build_root_pages.py` writes `dist/sleeper-players.json` (Sleeper id -> name, position, team; 4,234 players,
  142 KB) from `data/inputs/sleeper_identity_base.json`, the table the data pipeline already pulls. So the browser
  never downloads Sleeper's 5 MB /players/nfl file.
- connect: with Sleeper selected, the copy-and-paste parts step aside: the intro line, the jump-to-paste link, the
  click-through tutorial, the "or" divider and step 2. The field reads "Sleeper league link or ID" with "Get my
  league", keeps the league ID help, and offers "Paste the rosters page instead" (the paste box, one tap away).
  - Paste, Enter, leaving the field or the button loads the league. It shows "Loading your league from Sleeper...",
    then the recognition card and "We found: <name>, N teams, M players."
  - It saves `ddf:pasted` (source sleeper) and applies the league's settings to the saved engine settings, so
    settings.html opens with them. Then the bookmark prompt asks once, and the sticky Next is enabled.

Review fixes (independent review of 0c3665b4, CHANGES NEEDED):
- Sleeper teams are read per team (no name matching in one long text): emoji-only names and "Team-A" / "Team A" keep
  their rosters;
- no "Edit team names" box for a Sleeper league (its names come from the league), and the card title reads "Here's
  what we read from Sleeper";
- a newer request wins: switching away from Sleeper or entering another ID mid-load drops the older answer;
- a missing player table is a network error and is not cached; unknown ids read "A player not in our list yet
  (Sleeper id N)"; a superflex-only lineup is left for settings.html; "values still loading" has its own message;
- tests state the expected players from the pipeline's id map instead of the code under test, and run one at a time.

### Verified (check named)
- `node tests/test_sleeper_import.js` (5 pass), on fixture responses with no live calls:
  - link and ID forms;
  - a loaded league equals the paste path (same teams and players);
  - team names, defenses, unknown ids, settings;
  - errors and their messages, with no banned words.
- `tests.test_sleeper_entry` (4 pass, incl. switching away mid-load, Sleeper API answered by fixtures):
  - one-field Sleeper view at 1440/390/360, with ESPN and Yahoo unchanged;
  - an ID loads 4 teams, the sticky Next turns on and setup lists them, with exactly 4 calls, all to Sleeper;
  - not found, old season and network errors in plain words, with the paste fallback.
- Local page against the real Sleeper API (the public 12-team league): 12 teams, 344 players, Next enabled, 0 errors,
  0 overflow at 390 and 1440.

### Claimed, not confirmed
- CI on the PR head; live behaviour after deploy (verified with the same public league, not stored in the repo).

### Guided Sleeper step (Jeremy, 2026-11-08)
- One step, no "Step 1" numbering. Heading "Add your Sleeper league" and the line "Paste your league link or ID and
  we'll load every team's roster. No copying needed."
- The field is labelled "Sleeper league link or ID", with the placeholder "sleeper.com/leagues/... or a number" and
  the example line "For example sleeper.com/leagues/1234567890123456 or just 1234567890123456." beneath it.
- One primary button, "Load my league" (paste and Enter also load). Then the loading line and "We found: <name>, N
  teams, M players. Check the list below, then press Next to confirm your team." The sticky bar's Next is the
  Continue.
- The league ID help comes first among the secondary items, and "Paste the rosters page instead" is a small link
  after it. The duplicate box heading is hidden.
- `tests.test_sleeper_entry`, at 390/360/1440, checks: no paste box by default, no numbering, the wording and
  example, Next disabled until the league loads, and the ID help before the fallback.
