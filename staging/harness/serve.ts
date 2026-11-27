// Local UI harness for the staging page (JEG-1732): the real ddf-account router with an in-memory store,
// stubbed DDF sign-in (localStorage.h_in = "1"), recorded Sleeper fixtures, live ESPN public reads, and a fake
// ESPN session (espn_s2 starting "AEBtest") that owns public league 1086064.
//   deno run --allow-read --allow-net staging/harness/serve.ts "$PWD"   ->  http://localhost:8791/ddf-staging/
// It reads files at start: restart after edits.
// Local UI harness for the JEG-1732 staging page: real router (app.ts) + MemoryStore,
// stubbed sign-in, recorded Sleeper fixture and synthetic Yahoo responses. No network to platforms.
const REPO = Deno.args[0];
const { makeApp } = await import(`file://${REPO}/supabase/functions/ddf-account/app.ts`);
const { MemoryStore } = await import(`file://${REPO}/supabase/functions/ddf-account/store.ts`);
const { importTokenKey } = await import(`file://${REPO}/supabase/functions/ddf-account/crypto.ts`);
const live = JSON.parse(await Deno.readTextFile(`${REPO}/tests/fixtures/sleeper-live/full.json`));
const j = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { "content-type": "application/json" } });
const ORIGIN = "http://localhost:8791";
const store = new MemoryStore(); store.allow.add("tester@example.com");
const fetchFx = async (u: string | URL, init?: RequestInit) => {
  const url = String(u);
  if (url.includes("fan.api.espn.com")) { // test path: a fake ESPN session that "owns" the public league 1086064
    return new Headers(init?.headers).get("cookie")?.includes("espn_s2=AEBtest") ? j({ preferences: [{ metaData: { entry: { abbrev: "FFL", seasonId: 2026, entryLocation: "Test", entryNickname: "Team", groups: [{ groupId: 1086064, groupName: "La Lega dei Cugini", groupSize: 12 }] } } }] }) : j({ message: "fan not found" }, 404);
  }
  if (url.includes("lm-api-reads.fantasy.espn.com")) { const h = new Headers(init?.headers); h.delete("cookie"); return fetch(url, { ...init, headers: h }); } // live ESPN public league
  const m = /league\/\d+\/matchups\/(\d+)$/.exec(url); if (m) return j(live.matchups[m[1]] ?? []);
  if (url.endsWith("/users")) return j(live.users);
  if (url.endsWith("/rosters")) return j(live.rosters);
  if (url.endsWith("/state/nfl")) return j(live.state);
  if (/league\/\d+$/.test(url)) return j(live.league);
  if (url.endsWith("/players/nfl")) return j({});
  if (/\/user\/u1\/leagues\/nfl\/\d+$/.test(url)) return j([{ league_id: live.league.league_id, name: "Recorded public league", season: "2026", total_rosters: 12 }]);
  if (/\/user\/[A-Za-z0-9_]+$/.test(url)) return j({ user_id: "u1", display_name: "Manager 1" });
  return j(null, 404);
};
const handle = makeApp({
  store, fetch: fetchFx,
  authUser: async (jwt: string) => jwt === "jwt-test" ? { id: "11111111-1111-4111-8111-111111111111", email: "tester@example.com", email_confirmed: true } : null,
  deleteAuthUser: async () => {}, tokenKey: () => importTokenKey(btoa("x".repeat(32))),
  env: () => undefined, functionsBase: ORIGIN + "/functions/v1", allowedOrigins: [ORIGIN],
  now: () => new Date(), log: () => {},
});
const page = (await Deno.readTextFile(`${REPO}/staging/account/index.html`)).replace(
  /<script src="https:\/\/cdn\.jsdelivr[^>]+><\/script>/,
  `<script>window.DDF_STAGING_FN="${ORIGIN}/functions/v1/ddf-account";
  window.supabase={createClient:function(){var on=function(){return localStorage.h_in==="1"};return{auth:{
    getSession:async function(){return{data:{session:on()?{access_token:"jwt-test"}:null}}},
    signInWithOtp:async function(){localStorage.h_in="1";setTimeout(function(){location.reload()},50);return{}},
    signInWithOAuth:async function(){return{error:{message:"provider is not enabled"}}},
    signOut:async function(){localStorage.h_in="0";return{}},onAuthStateChange:function(){}}}}};</script>`);
const appJs = await Deno.readTextFile(`${REPO}/staging/account/app.js`);
const css = await Deno.readTextFile(`${REPO}/staging/account/connect-page.css`);
Deno.serve({ port: 8791 }, (req) => {
  const p = new URL(req.url).pathname;
  if (p.startsWith("/functions/v1/ddf-account")) return handle(req);
  if (p === "/ddf-staging/connect-page.css") return new Response(css, { headers: { "content-type": "text/css" } });
  if (p === "/ddf-staging/app.js") return new Response(appJs, { headers: { "content-type": "text/javascript" } });
  if (p === "/ddf-staging/" ) return new Response(page, { headers: { "content-type": "text/html" } });
  return new Response("nf", { status: 404 });
});
