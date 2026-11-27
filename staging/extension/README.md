# DDF: Connect ESPN (staging extension, JEG-1732)

Manifest V3 Chrome extension that lets a signed-in DDF user connect ESPN without typing league IDs
or anything technical. Unpublished: load it unpacked (steps in `docs/signed-in-staging.md`).

- Permissions: `cookies` only, with host access to `*.espn.com` and DDF's Supabase function origin.
- `externally_connectable`: only the staging page origin (and the local harness at localhost:8791).
- Flow: the page sends `{type: "connect-espn", jwt}`; the extension reads `espn_s2` and `SWID` for
  espn.com and POSTs them to `ddf-account /espn/session`. The function checks them against ESPN,
  seals them (AES-GCM) and returns the user's ESPN football leagues for this season.
- The extension ID is fixed by the public `key` in the manifest: `hnkkhmlmjcaofnjjekgggdhchgohlkcp`.
  The Chrome Web Store assigns its own ID on publishing (Jeremy's call); update `EXT_ID` in
  `staging/account/app.js` then.
