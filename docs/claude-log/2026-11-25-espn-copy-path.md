# The shorter ESPN copy path (2026-11-25)

League entry cheap win 3 of 3 (Jeremy, 2026-11-24: cheap wins, then the Chrome helper, then accounts).

- The ESPN Open button opens ESPN's data view of the league in a new tab:
  `lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{id}?view=mTeam&view=mRoster&view=mSettings`.
  A top-level visit carries the reader's espn.com sign-in, so private leagues show for their members (research
  2026-11-24). Signed out, ESPN answers `{"messages":["You are not authorized..."],"details":[{"type":"AUTH_LEAGUE_NOT_VISIBLE"}]}`.
- "Use what I copied" (the Paste rosters button, renamed) reads the clipboard. Text that is ESPN's JSON is read by
  `connect-entry.js espnCopied/readEspnCopied` with `espn-import.js fromLeague` (settings, slots and team count come
  with it) and never put in the box; anything else goes through the paste reader as before. The same JSON pasted
  into the box reads the same way. A cut-off copy, a not-authorized answer and a not-found answer each get a message.
- Returning from the opened tab (visibilitychange) points at Use what I copied.
- Not yet checked on a physical iPhone: whether Select All over the 4.5 MB data view copies cleanly. The rosters page
  link stays under the button as the fallback.
