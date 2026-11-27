# Signed-in DDF staging (JEG-1732)

Private test build of DDF sign-in and league connections. Not the live site.

- Page source: `staging/account/` (static HTML + JS, noindex, linked from nowhere).
- Published to the separate repo `datadrivenfootball/ddf-staging` on GitHub Pages
  (Jeremy, 2026-11-27: "Separate staging repo"), served at
  https://datadrivenfootball.github.io/ddf-staging/. The fantasy-tools Pages deploy
  never includes it (`make sync` does not copy `staging/`).
- Back end: edge function `supabase/functions/ddf-account/` and schema
  `ddf_accounts` (`supabase/migrations/jeg1732_ddf_accounts_20261127.sql`).
- Setup, secrets and the Yahoo/Google steps: `docs/signed-in-staging.md`.

Publish the page: `staging/publish.sh` (copies `staging/account/` to the staging
repo's main branch and pushes).

## ESPN connect flow and the iOS app
- The page starts from the ESPN league link. Public leagues connect at once. A private league opens one
  screen with the ways in: in-app sign-in (DDF app), the Chrome helper (`staging/extension/`), a ready-made
  request to the league manager, and the bookmark as a folded last resort.
- `staging/ios-app/`: SwiftUI prototype that wraps the page and adds the in-app ESPN sign-in. See its README.
