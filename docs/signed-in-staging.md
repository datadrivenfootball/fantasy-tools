# Signed-in DDF: staging sign-in and league connections (JEG-1732)

Private test build so the signed-in concepts (JEG-1729) can be tried on real
leagues. Nothing here is on the live site. Decisions, Jeremy 2026-11-27:
separate staging repo; new `ddf_accounts` schema in the existing project; a new
DDF Yahoo app; Claude sets the Auth URL config.

| Piece | Where |
| --- | --- |
| Staging page | https://datadrivenfootball.github.io/ddf-staging/ (repo `datadrivenfootball/ddf-staging`, source `staging/account/`, publish with `staging/publish.sh`) |
| Edge function | `ddf-account` in project `iskiybsimubiujwuchsl` (`supabase/functions/ddf-account/`) |
| Schema | `ddf_accounts` (`supabase/migrations/jeg1732_ddf_accounts_20261127.sql`): allowlist, connections, oauth_states, leagues, platform_cache. RLS on, no policies, not exposed to PostgREST |
| Tests | `deno test --allow-read supabase/functions/ddf-account/test/` (also run by `tests/test_edge_functions_parse.py`) |

## How it works

- **Sign in:** Supabase Auth, email magic link (implicit flow, so the link works
  in whatever browser the mail app opens). Google once Jeremy adds the client.
- **Gate:** every call needs a Supabase user JWT whose email is in
  `ddf_accounts.allowlist` (rows added by hand, never committed).
- **Connections** (read-only on every platform; DDF never asks for a platform password):
  - Sleeper by username, public API.
  - Yahoo by OAuth 2.0 (authorization code). Tokens are sealed with AES-256-GCM
    in the function (key: `DDF_TOKEN_KEY` secret; additional data binds each
    ciphertext to its user and platform) and refreshed when expired.
  - ESPN public leagues by league ID or link. Private leagues are refused with
    a message; the extension below is the later path.
- **On connect / refresh** the function stores `summary` (shape
  `ddf-connected-league/0`: settings incl. the site's `settingsOf` shape, all
  rosters, standings, schedule with platform team projections where given,
  trade deadline, FAAB, waiver priority, `pulled_at`, and a `missing` list with
  reasons) plus the platform's `raw` payloads.
- **Confirm settings** stores `confirmed_settings`, which drive DDF for that
  league once wired; defaults apply only with no league.
- **Disconnect** deletes the connection, its sealed token and its leagues.
  **Delete account** deletes everything and the auth user.
- **Logs** hold route, status, time and error code only.

Secrets (Supabase function secrets, never in files): `DDF_TOKEN_KEY` (set
2026-11-27), `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET` (Jeremy). Optional:
`YAHOO_SCOPE` (empty = the app's configured permissions), `YAHOO_REDIRECT_URI`,
`DDF_STAGING_ORIGINS`.

Auth config set 2026-11-27 (Management API, Jeremy's go): Site URL and redirect
allowlist `https://datadrivenfootball.github.io/ddf-staging/**`; magic-link
email subject and text say DDF. The built-in mailer sends only to the Supabase
org's team members and about 2 emails an hour: fine for staging; real users
need custom SMTP (Resend is already a secret in this project).

## Jeremy's steps

### Google sign-in (about 10 minutes)

1. Open https://console.cloud.google.com, top bar project picker, **New project**,
   name it `Data Driven Football`, Create, then select it.
2. Left menu **APIs & Services › OAuth consent screen** (Google Auth Platform).
   **Get started**: App name `Data Driven Football`, your email as support email,
   Audience **External**, contact email yours, agree, Create.
3. **Audience** tab: leave Publishing status **Testing**; under Test users,
   **Add users**, your Gmail, Save.
4. **Clients** tab, **Create client**: Application type **Web application**,
   name `DDF staging`.
   - Authorized JavaScript origins: `https://datadrivenfootball.github.io`
   - Authorized redirect URIs: `https://iskiybsimubiujwuchsl.supabase.co/auth/v1/callback`
   - Create. Keep the dialog with the Client ID and Client secret open.
5. Supabase dashboard › project `JB-barrel-droid's Project` › **Authentication ›
   Sign In / Providers › Google**: turn it on, paste Client ID and Client
   secret, Save. (The secret goes only into Supabase.)
6. On the staging page, **Sign in with Google**.

### Yahoo app and Fantasy API access

1. Signed in to Yahoo, open https://developer.yahoo.com/apps/create/.
2. Fill in:
   - Application Name: `Data Driven Football`
   - Application Type: **Web Application** (confidential client)
   - Description: `Read-only league analysis for Data Driven Football`
   - Homepage URL: `https://datadrivenfootball.github.io/fantasy-tools/`
   - Redirect URI(s): `https://iskiybsimubiujwuchsl.supabase.co/functions/v1/ddf-account/yahoo/callback`
   - API Permissions: **Fantasy Sports › Read** if it is offered; otherwise
     **OpenID Connect** (Email, Profile). Never Read/Write.
3. **Create App**. Copy the Client ID and Client Secret.
4. Supabase dashboard › **Edge Functions › Secrets** › Add: `YAHOO_CLIENT_ID`
   and `YAHOO_CLIENT_SECRET` with those values, Save. (Or Terminal:
   `supabase secrets set --project-ref iskiybsimubiujwuchsl YAHOO_CLIENT_ID=... YAHOO_CLIENT_SECRET=...`.)
5. Apply for Fantasy API access for that Client ID at
   https://sports.yahoo.com/developer/access/: product = read-only league
   analysis (settings, rosters, standings, scoreboard, transactions), user base
   **under 1,000**, read-only, existing Client ID = the new one. Yahoo reviews
   each app; reports put it at 2 to 4 weeks.
6. Until approval, **Connect Yahoo** completes the sign-in and stores the
   token, but reading a league returns "Yahoo refused the Fantasy API call
   (403)". After approval, open the staging page, Yahoo › Leagues › USO Season
   XVIII › Pull. If Yahoo then says the token lacks the scope, set
   `YAHOO_SCOPE=fspt-r` and connect again.

## Yahoo weekly projections (finding, 2026-11-27)

- **Per-player weekly projected points are not in the public Fantasy API v2.**
  Only `stats;type=week` (actuals) and `type=season` are documented; no
  open-source client (yfpy, yahoo-fantasy npm, ffanalytics) reads a projected
  player field. Yahoo's projections are a website feature.
- **Team weekly projections are**: `team_projected_points/total` in
  `league/{key}/scoreboard;week=N` and `team/{key}/matchups`. The pull stores
  them per matchup (`schedule[].matchups[].projected_points`).
- The pull also runs a **probe** (`summary.probes`): `players;player_keys=.../stats`
  with `type=week` and `type=projected_week` for the current week, recording
  status and whether any projected field appears. The first approved pull
  confirms or overturns the desk finding.
- Consequence for "weekly points come from the league's own platform": for
  Yahoo it can hold for team totals only. Player-level weekly numbers would
  need the fill-in source, labelled per cell. That is Jeremy's call (on JEG-1732).

## Proposed, not built: ESPN private leagues by browser extension

- A small Manifest V3 extension (Chrome/Edge; Safari later) with host access to
  `*.espn.com` only, plus `cookies`.
- The user signs in to DDF on the staging page; the page hands the extension a
  short-lived DDF token (`externally_connectable`).
- On fantasy.espn.com, signed in, the user presses **Connect ESPN to DDF** in the
  popup. Only then the extension reads `espn_s2` and `SWID` and posts them to
  `ddf-account` (`POST /espn/session`), which seals them like Yahoo tokens and
  sends them as the Cookie header to `lm-api-reads.fantasy.espn.com`.
- Read-only by code; the cookies themselves are a full ESPN session, so the
  connect screen says so, and Disconnect deletes them. `espn_s2` lasts about a
  year; a 401 asks the user to reconnect.
- Phones cannot run it (no extensions in iOS Chrome): connect once on a
  computer; the phone then reads through DDF. Paste stays the phone fallback.
- Needs a Chrome Web Store listing (review) and a privacy page.
