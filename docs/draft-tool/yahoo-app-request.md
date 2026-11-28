# Yahoo developer app and license request (draft for Jeremy to submit)

Jeremy, 2026-11-27: "Parallel path paste in and yahoo sign-in, knowing that
we will need a license to get the yahoo ok." Nothing here has been
submitted, and no account or app has been created. Jeremy submits both.

## Part 1: register the app (developer.yahoo.com/apps/create)

| Field | Value |
| --- | --- |
| Application name | Data Driven Football Draft Tool |
| Application type | Web application |
| Description | Reads a user's own Yahoo fantasy football league (settings, teams, rosters, draft results and player draft analysis) so the Data Driven Football draft tool can set up the user's league and price players for a live auction or snake draft. Read only; nothing is written back to Yahoo. |
| Homepage URL | https://datadrivenfootball.github.io/fantasy-tools/ |
| Redirect URI | `https://iskiybsimubiujwuchsl.supabase.co/functions/v1/yahoo-oauth/callback` (a token-exchange function, built only after approval) |
| API permissions | Fantasy Sports: **Read** (`fspt-r`). No other Yahoo APIs. |

Why a redirect to Supabase: Yahoo's code flow needs the client secret, which
cannot sit in a static page. The function only swaps the code for a token
and hands the token back to the browser; it stores no tokens and no league
data (the tool saves state in links, not on a server).

Keep the Client ID and Client Secret out of the repo, chats and tickets:
Jeremy enters them as Supabase function secrets himself.

## Part 2: license request (Yahoo Fantasy API commercial use)

Send to the Yahoo developer support or partnerships contact listed on the
Fantasy Sports API terms page. Draft:

> Subject: Fantasy Sports API: request for approval and license, Data Driven Football draft tool
>
> Hello,
>
> [Jeremy: confirm each bracketed line before sending.]
>
> I run Data Driven Football (https://datadrivenfootball.github.io/fantasy-tools/),
> a free fantasy football site that helps managers value players and trades.
> I am building a live draft assistant for season-long auction and snake
> drafts and would like to let Yahoo users connect their own league with
> Yahoo sign-in.
>
> What we would read, only for the signed-in user's own leagues, read only:
> league settings (scoring, roster slots, auction budget), teams, rosters,
> draft results (including auction costs) and player draft analysis (average
> pick and average cost).
>
> How: OAuth 2.0 with the Fantasy Sports read scope. Data is used in the
> user's browser during their draft. We do not store tokens or league data on
> our servers, do not resell or redistribute Yahoo data, and do not write
> anything back to Yahoo. We show Yahoo as the source wherever its data
> appears.
>
> [confirm] The site has no ads or paid tier today. If a paid tier is added later, we
> would like to know now what license that requires.
>
> Could you confirm what approval or license we need, and its terms?
>
> Thank you,
> Jeremy

## Until approval

Paste covers Yahoo: the user copies the league settings page and the draft
results page and the tool parses them (the brief's fallback path).
