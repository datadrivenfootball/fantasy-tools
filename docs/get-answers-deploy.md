# get-answers: deploy and rollback plan

Status: not deployed. Owner JEG-1543 (phase 2). Last verified 2026-11-08 (locally, against a built `dist/`).
Deploying needs Jeremy's yes; the lead of the JEG-1543 lane deploys. What the function does: `docs/answers-site.md`
("Recommendations endpoint").

## What ships
- New function `supabase/functions/get-answers/` (`index.ts` handler, `core.ts` pure core). It imports
  `../get-values/league.ts`, `pipeline.ts` and `value-context.ts`, so the deploy bundles those files too; get-values
  itself is not redeployed and its contract does not change.
- `supabase/config.toml`: `[functions.get-answers] verify_jwt = false` (public, no accounts, like get-values).
- No database, migration, secret or storage change.

## Environment
| Name | Needed | Value |
|---|---|---|
| `DDF_SITE_ORIGIN` | optional | The published site it reads. Unset = `https://jb-barrel-droid.github.io/fantasy-tools` (get-values' default). Set it to the same value get-values uses. |
| `DDF_TODAY` | never in production | Test-only clock pin (YYYY-MM-DD). Leave unset. |

No secrets. It fetches from the site, at cold start and every 5 minutes: `assets/value-model.js`,
`assets/comparison-sources-data.json`, `/` (the `players-data` island), `assets/lineup-parameters.json`,
`assets/history/index.json` (+ the week documents it needs) and the page modules in `core.ts` `PAGE_SCRIPTS`
(`v2/ddf-value-link.js`, `v2/trade.js`, `v2/finder.js`, `ddf-opportunity.js`, `v2/team-summary.js`, `v2/nfl-byes.js`,
`v2/player-status.js`, `v2/waivers.js`, `ddf-engine.js`, `ddf-league.js`, `find-engine.js`, `ddf-why.js`). The site
must publish all of them; a missing page module is a 500 ("a site file did not load"), never a partial answer.

## Deploy (lead, after Jeremy's yes)
1. Save a rollback note: `get-answers` is new, so there is no previous version to copy. Record "new function, none
   before" under `/Users/botcomp/Desktop/ddf-handoff 2/09-mcp-server/engine-local/rollback-get-answers-<date>.md`
   (the lead's step), with the commit SHA deployed.
2. From the repo root on the merged commit:
   `supabase functions deploy get-answers --project-ref iskiybsimubiujwuchsl --no-verify-jwt`
3. Smoke (any league; a real one gives offers). Expected: HTTP 200 and the top-level keys
   `v, as_of, week, setting, sizes, team, partners, natural, neutral, force, notes`, `notes.searched` listing the
   opponent ids, and no source names anywhere in the body:

```sh
URL=https://iskiybsimubiujwuchsl.supabase.co/functions/v1/get-answers
curl -s -X POST "$URL" -H 'content-type: application/json' -d '{
  "league": {"scoring": "ppr", "teams": 12},
  "me": {"keys": ["2227", "3247", "1110"]},
  "opponents": [{"id": 1, "name": "Team 2", "keys": ["1833", "3803", "3942"]}]
}' | python3 -c 'import json,sys; b=json.load(sys.stdin); print(sorted(b)); print(b["notes"])'
# a refusal, expected HTTP 400 code not_in_answers:
curl -s -X POST "$URL" -H 'content-type: application/json' -d '{"league": {}, "me": {"keys": []}, "opponents": [{"id": 1, "name": "x", "keys": []}], "include": "charts"}'
```

   Then run the privacy check on a real reply: save it to `reply.json` and
   `python3 -c "import json,sys; sys.path.insert(0,'pipelines'); import answers_privacy as ap; print(ap.text_findings('reply', open('reply.json').read()))"`
   (expected `[]`).
4. Watch the logs (`get_answers.compute` lines carry `ms`): Supabase caps CPU time per request (2 s at the time of
   writing). Locally a 12-team league, 11 partners, sizes 1-2 took about 0.9 s warm and 1.1-1.3 s cold (node and
   Deno). A first request after a cold start also parses the source bundle (~2.6 MB).

## Rollback
- The function is new and nothing on the site calls it yet, so rollback is: `supabase functions delete get-answers
  --project-ref iskiybsimubiujwuchsl` (or redeploy the previous commit's copy once one exists). get-values and mcp
  are untouched by this deploy.
- If a reply ever carried source text, delete the function first and investigate second: the reply allowlist
  (`core.ts` `REPLY_SPEC`, `validateReply`) is meant to make that a 500 instead.

## Not covered yet
- Off-grid answers-mode get-values (values for settings outside the grid) is a separate change (design section 3(ii)).
- The answers pages do not call this function yet (phase 3 client).
- Response compression depends on the gateway: the default reply is ~0.5 MB raw, ~30 KB gzip for a 12-team league.
