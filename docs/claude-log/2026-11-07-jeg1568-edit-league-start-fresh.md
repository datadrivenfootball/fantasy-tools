## 2026-11-07 - JEG-1568 Edit league opens the start of the entry flow; Start fresh

Contract (Jeremy, 2026-11-07): "Edit league" in the Your league menu goes to the beginning of the entry flow, not the
end, and there is a way to wipe the current settings before entering a league. Client-side only, no analytics.

What changed
- Every "Edit league" link (the header menu, the league strip on Team, Explore, Partners, Trade & Waiver
  Recommendations, Build a Trade and Waivers, and the chat strip) now opens `connect.html?edit=1` (was settings.html).
- Editing (`connect-entry.js`): "Replacing: <name>. Your current league stays in use until you check a new paste or
  enter rosters." at the top and above the paste box, with "Keep my league" and "Start fresh". The current league is
  snapshot on arrival. Typing, emptying the box or emptying manual entry puts it back, so backing out loses nothing.
  A successful read replaces it. A replaced chat league's settings are saved to the engine, so settings.html still
  shows them. `ddf:editprev` {name, team, source} lets setup suggest the current name when the new paste has none,
  preselect the team of the same name, and replace the saved league without asking (the reader chose to replace it).
  Arriving at connect.html without `?edit=1` drops `ddf:editprev`.
- Start fresh (`site.js` `DDF.startFresh`): opened from the header menu and from the top of connect.html. It is an
  in-page dialog (role=dialog, aria-modal, labelled and described, focus on "Keep my league", Esc and outside click
  close, Tab stays inside, 44px targets). One line says what goes. "Also clear my value overrides" is off by default.
  `KEYS` lists every store:
  - cleared: session `ddf:pasted, league, link, ctxlink, waivers, available, moves, hold, skip, trade, settingsok,
    bridgedWs, bridgeKeep, editprev, bookmarked, bmhint, bmwant, bmdone, bmovbase`, `ddf:freshdismiss:*` and
    `ddf-recommendation`; local `ddf.v2.workspaces, ddf.v2.league-settings, ddf.v2.waiverCandidates`;
  - checkbox: `ddf:overrides, ddf:basis, ddf:posweights, ddf-v2-link-state`, local `ddf-v2-value-overrides`;
  - kept: `ddf:table:*` (player table cache) and `ddf:wipedlink`.
  After clearing, the #s= link in the address is marked used for the session (`ddf:wipedlink`; `DDF.link.hasState`
  and `decode` skip it) and stripped with history.replaceState. Then the header refreshes and connect.html opens.

Review fixes (independent review of 4ae77bb8, CHANGES NEEDED):
- half-typed manual rows no longer replace the league while editing (only two teams with players do);
- opening Edit league on a manual league keeps its picked team, name and date (no save while the page restores it);
- "Keep my league" puts the old league back after a replacement paste, and the strip says the new rosters are read;
- Start fresh also marks the link this tab applied (ddf:ctxlink), so Back to a link page on another page does not
  import it; a cleared link reopened in the tab shows "Open the link in a new tab to load it again";
- `ddf:editprev` ends when setup's Next is pressed.

### Verified (check named)
- `tests.test_edit_league` (9 pass):
  - every Edit league link targets connect.html?edit=1;
  - an abandoned edit keeps the league (typing, failed read, emptied box and emptied manual entry);
  - a replacement prefills the name and team;
  - Start fresh clears every listed key, with and without the overrides checkbox, and the source scan fails when a
    storage key is in no list;
  - a wiped link is not imported again (Back, then reopening the same link);
  - dialog roles, labels, focus, Esc, Tab, 44px targets and no overflow at 390 and 1440.
- Regression set: see the PR body.

### Claimed, not confirmed
- CI on the PR head; live behaviour after deploy.

### Follow-up: one sticky Back/Next on every entry page (Jeremy, 2026-11-07)
- connect.html and settings.html follow setup.html (#1350): the sticky action bar is the only Back/Next. The in-page
  rows (connect `.advance-end` and the Back inside `.entry-actions`; settings `.st-actions`) stay in the markup,
  because the bar forwards its click to them (gating, settings confirm), but they are not shown.
- Tests that clicked the hidden `#connect-next` now click the bar's Next.
- `tests.test_entry_sticky_bar` (3 pass), at 1440, 390 and 360:
  - one visible Next and one visible Back per page, and the bar's Back goes to the previous step;
  - Next is greyed until its requirement is met (connect: rosters read; setup: a team; settings: a complete lineup);
  - the bar's Next on settings still confirms the settings;
  - 44px targets, accessible names, Tab reaches the bar;
  - Edit league and Start fresh stay on connect.
- Run with the entry, edit-league, bookmark and JEG-1557 suites: 48 pass.
