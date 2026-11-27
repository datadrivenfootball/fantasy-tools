// deno-lint-ignore-file require-await -- the Store interface is async; the in-memory and stub versions have nothing to await
// Hermetic tests for ddf-account (JEG-1732): no network, no database.
//   deno test --allow-read supabase/functions/ddf-account/test/
import { assert, assertEquals, assertRejects } from "jsr:@std/assert@1";
import { makeApp, validSettings, type Deps } from "../app.ts";
import { importTokenKey, seal, unseal } from "../crypto.ts";
import { espnDdfSettings, summarizeEspn } from "../espn.ts";
import { pullSleeper, sleeperDdfSettings } from "../sleeper.ts";
import { MemoryStore } from "../store.ts";
import { pullYahoo, ymerge, yitems } from "../yahoo.ts";

const ROOT = new URL("../../../../", import.meta.url);
const fixture = async (p: string) => JSON.parse(await Deno.readTextFile(new URL(p, ROOT)));
const KEY_B64 = btoa(String.fromCharCode(...new Uint8Array(32).map((_, i) => i + 1)));

// The site's own settings translators, loaded as the pages load them.
await import(new URL("app/next/sleeper-import.js", ROOT).href);
await import(new URL("app/next/espn-import.js", ROOT).href);
// deno-lint-ignore no-explicit-any
const DDF = (globalThis as any).DDF;

function jsonRes(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

// ---------- Sleeper ----------
async function sleeperFetch() {
  const live = await fixture("tests/fixtures/sleeper-live/full.json");
  return {
    live,
    fetch: async (u: string | URL) => {
      const url = String(u);
      const m = /league\/\d+\/matchups\/(\d+)$/.exec(url);
      if (m) return jsonRes(live.matchups[m[1]] ?? []);
      if (url.endsWith("/users")) return jsonRes(live.users);
      if (url.endsWith("/rosters")) return jsonRes(live.rosters);
      if (url.endsWith("/state/nfl")) return jsonRes(live.state);
      if (/league\/\d+$/.test(url)) return jsonRes(live.league);
      if (url.endsWith("/players/nfl")) return jsonRes({ "4984": { full_name: "Josh Allen", position: "QB", team: "BUF" } });
      if (/\/user\/[A-Za-z0-9_]+$/.test(url)) return jsonRes({ user_id: "u1", display_name: "Manager 1" });
      if (/\/user\/u1\/leagues\/nfl\/\d+$/.test(url)) return jsonRes([{ league_id: live.league.league_id, name: "Test league", season: "2026", total_rosters: 12 }]);
      return jsonRes(null, 404);
    },
  };
}

Deno.test("Sleeper settings match the site's settingsOf on every Sleeper fixture", async () => {
  for (const p of ["tests/fixtures/sleeper/league.json", "tests/fixtures/sleeper-live/full.json", "tests/fixtures/sleeper-live/divisions.json", "tests/fixtures/sleeper-live/preseason.json"]) {
    const f = await fixture(p);
    const lg = f.league ?? f;
    assertEquals(sleeperDdfSettings(lg), DDF.sleeper.settingsOf(lg), p);
  }
});

Deno.test("Sleeper pull reads settings, rosters, standings, schedule, deadline, FAAB and waiver priority", async () => {
  const { live, fetch } = await sleeperFetch();
  const names = async (ids: string[]) => Object.fromEntries(ids.filter((i) => i === "4984").map((i) => [i, { n: "Josh Allen", p: "QB", t: "BUF" }]));
  const { summary } = await pullSleeper(fetch, live.league.league_id, "u1", names, new Date("2026-11-27T12:00:00Z"));
  assertEquals(summary.settings.trade_deadline, { week: 14, date: null, none: false, source: "sleeper:league.settings.trade_deadline" });
  assertEquals(summary.settings.waiver_type, "faab");
  assertEquals(summary.settings.faab_budget, 100);
  assertEquals(summary.settings.playoff_start_week, 15);
  assertEquals(summary.settings.last_regular_week, 14);
  assertEquals(summary.teams.length, 12);
  const t1 = summary.teams.find((t) => t.team_key === "1")!;
  assertEquals(t1.faab_remaining, 100 - live.rosters.find((r: { roster_id: number }) => r.roster_id === 1).settings.waiver_budget_used);
  assert(t1.waiver_priority !== null);
  assert(summary.teams.every((t) => t.standings.rank !== null && t.standings.wins !== null));
  assertEquals(summary.schedule.length, 14);
  // weeks after the current week (10) carry no score, never a 0
  const wk = (n: number) => summary.schedule[n - 1].matchups.flatMap((m) => m.points);
  assert(wk(10).some((p) => p !== null && p > 0));
  assert(wk(11).length > 0 && wk(11).every((p) => p === null));
  assertEquals(summary.my_team_key, "10"); // fixture user u1 owns roster 10
  assertEquals(summary.pulled_at, "2026-11-27T12:00:00.000Z");
  // The current week (10) has real scores: live, not final.
  assert(summary.schedule[9].matchups.every((m) => m.status === "live"));
  assert(summary.schedule[8].matchups.every((m) => m.status === "final"));
  // A rostered id with no name stays null and is listed, never guessed.
  assert(summary.missing.some((m) => m.path === "teams[].roster[].name"));
});

Deno.test("Sleeper: an unstarted current week and a missing FAAB spend are null, never 0 or the full budget", async () => {
  const { live, fetch } = await sleeperFetch();
  const rosters = structuredClone(live.rosters);
  delete rosters[0].settings.waiver_budget_used;
  const zeroWeek = (live.matchups["10"] as { points: number }[]).map((m) => ({ ...m, points: 0 }));
  const f = async (u: string | URL) => {
    const url = String(u);
    if (url.endsWith("/rosters")) return jsonRes(rosters);
    if (url.endsWith("/matchups/10")) return jsonRes(zeroWeek);
    return fetch(u);
  };
  const { summary } = await pullSleeper(f, live.league.league_id, "u1", async () => ({}));
  assert(summary.schedule[9].matchups.every((m) => m.status === "not_started" && m.points.every((p) => p === null)));
  const t = summary.teams.find((x) => x.team_key === String(rosters[0].roster_id))!;
  assertEquals(t.faab_remaining, null);
  assert(summary.missing.some((m) => m.path === "teams[].faab_remaining"));
});

Deno.test("Sleeper: refreshing a past season's league keeps its played weeks", async () => {
  const { live, fetch } = await sleeperFetch();
  const f = async (u: string | URL) => String(u).endsWith("/state/nfl") ? jsonRes({ ...live.state, season: "2027", league_season: "2027", week: 1 }) : fetch(u);
  const { summary } = await pullSleeper(f, live.league.league_id, "u1", async () => ({}));
  assert(summary.schedule[9].matchups.every((m) => m.status === "final" && m.points.some((p) => p !== null)));
});

// ---------- ESPN ----------
Deno.test("ESPN settings match the site's settingsOf, and the summary reads teams", async () => {
  const s = await fixture("tests/fixtures/espn/settings.json");
  const t = await fixture("tests/fixtures/espn/teams.json");
  const lg = { ...s, ...t, settings: s.settings };
  assertEquals(espnDdfSettings(lg), DDF.espn.settingsOf(lg));
  const sum = summarizeEspn(lg, String(lg.id), 2026, new Date("2026-11-27T12:00:00Z"));
  assertEquals(sum.teams.length, lg.teams.length);
  assert(sum.teams.every((x) => x.name.length > 0));
});

// ---------- Yahoo ----------
const team = (key: string, name: string, extra: Record<string, unknown>[], tail: Record<string, unknown>) =>
  [[{ team_key: key }, { team_id: key.split(".t.")[1] }, { name }, [], ...extra, { managers: [{ manager: { manager_id: "1", nickname: name + " mgr", guid: "G" + key } }] }], tail];
function yahooFixtures() {
  const lk = "470.l.848938";
  const meta = { league_key: lk, name: "USO", num_teams: 2, current_week: 1, start_week: "1", end_week: "2", season: "2026" };
  const settings = {
    uses_faab: "1", playoff_start_week: "15", num_playoff_teams: "6", trade_end_date: "2026-11-28", waiver_type: "R",
    roster_positions: [
      { roster_position: { position: "QB", count: 1 } }, { roster_position: { position: "RB", count: 2 } },
      { roster_position: { position: "WR", count: 3 } }, { roster_position: { position: "TE", count: 1 } },
      { roster_position: { position: "W/R/T", count: 1 } }, { roster_position: { position: "K", count: 1 } },
      { roster_position: { position: "DEF", count: 1 } }, { roster_position: { position: "BN", count: 6 } },
    ],
    stat_modifiers: { stats: [{ stat: { stat_id: "11", value: "0.5" } }] },
  };
  const teamsStand = {
    "0": { team: team(lk + ".t.2", "Tiny Hands", [{ waiver_priority: 3 }, { faab_balance: "55" }, { is_owned_by_current_login: 1 }], { team_standings: { rank: "1", outcome_totals: { wins: "9", losses: "3", ties: 0 }, points_for: "1500.5", points_against: "1300.25" } }) },
    "1": { team: team(lk + ".t.3", "Other", [{ waiver_priority: 1 }, { faab_balance: "80" }], { team_standings: { rank: "2", outcome_totals: { wins: "8", losses: "4", ties: 0 }, points_for: "1400", points_against: "1350" } }) },
    count: 2,
  };
  const player = (k: string, n: string, pos: string, slot: string) => ({ player: [[{ player_key: k }, { name: { full: n } }, { editorial_team_abbr: "Buf" }, { display_position: pos }], { selected_position: [{ coverage_type: "week" }, { position: slot }] }] });
  const teamsRoster = {
    "0": { team: [[{ team_key: lk + ".t.2" }], { roster: { "0": { players: { "0": player("470.p.1", "Josh Allen", "QB", "QB"), "1": player("470.p.2", "Bench Guy", "WR", "BN"), count: 2 } } } }] },
    "1": { team: [[{ team_key: lk + ".t.3" }], { roster: { "0": { players: { "0": player("470.p.3", "Other QB", "QB", "QB"), count: 1 } } } }] },
    count: 2,
  };
  const board = (w: number) => ({ league: [meta, { scoreboard: { "0": { matchups: { "0": { matchup: { "0": { teams: { "0": { team: [[{ team_key: lk + ".t.2" }], { team_points: { total: String(100 + w) }, team_projected_points: { total: "110.5" } }] }, "1": { team: [[{ team_key: lk + ".t.3" }], { team_points: { total: "90" }, team_projected_points: { total: "101.2" } }] }, count: 2 } }, week: String(w), is_playoffs: "0" } }, count: 1 } } } }] });
  return { lk, settings: { league: [meta, { settings: [settings] }] }, standings: { league: [meta, { standings: [{ teams: teamsStand }] }] }, roster: { league: [meta, { teams: teamsRoster }] }, board };
}
function yahooFetch(status = 200) {
  const fx = yahooFixtures();
  const seen: { url: string; auth: string | null }[] = [];
  const f = async (u: string | URL, init?: RequestInit) => {
    const url = String(u);
    seen.push({ url, auth: new Headers(init?.headers).get("authorization") });
    if (status !== 200) return jsonRes({}, status);
    const fc = (x: unknown) => jsonRes({ fantasy_content: x });
    if (url.includes("/settings")) return fc(fx.settings);
    if (url.includes("/standings")) return fc(fx.standings);
    if (url.includes("/teams/roster")) return fc(fx.roster);
    const w = /scoreboard;week=(\d+)/.exec(url);
    if (w) return fc(fx.board(Number(w[1])));
    if (url.includes("/stats;type=")) return jsonRes({}, 400);
    return jsonRes({}, 404);
  };
  return { fx, f, seen };
}

Deno.test("Yahoo helpers flatten Yahoo's array-of-objects JSON", () => {
  assertEquals(ymerge([{ a: 1 }, [{ b: 2 }, { c: 3 }]]), { a: 1, b: 2, c: 3 });
  assertEquals(yitems({ "1": { x: "b" }, "0": { x: "a" }, count: 2 }, "x"), ["a", "b"]);
});

Deno.test("Yahoo pull reads settings, standings, FAAB, waivers, rosters and team projections", async () => {
  const { fx, f, seen } = yahooFetch();
  const { summary } = await pullYahoo(f, "tok", fx.lk, new Date("2026-11-27T12:00:00Z"));
  assertEquals(summary.settings.ddf, { scoring: "half_ppr", superflex: false, roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6, K: 1, DST: 1 }, teams: 8 });
  assertEquals(summary.settings.trade_deadline.date, "2026-11-28");
  assertEquals(summary.my_team_key, fx.lk + ".t.2");
  const th = summary.teams[0];
  assertEquals([th.name, th.faab_remaining, th.waiver_priority, th.standings.wins, th.standings.rank], ["Tiny Hands", 55, 3, 9, 1]);
  assertEquals(th.roster.map((p) => [p.name, p.slot, p.nfl_team]), [["Josh Allen", "QB", "BUF"], ["Bench Guy", "BN", "BUF"]]);
  assertEquals(summary.schedule.map((w) => w.matchups[0].projected_points), [[110.5, 101.2], [110.5, 101.2]]);
  assertEquals(summary.schedule.map((w) => w.matchups[0].points), [[101, 90], [null, null]]); // week 2 not played yet
  assert(summary.missing.some((m) => m.path === "settings.faab_budget"));
  assert(seen.every((s) => s.auth === "Bearer tok" && s.url.includes("format=json")));
});

Deno.test("Yahoo: a preevent matchup has no score even in the current week", async () => {
  const yf = yahooFetch();
  const f = async (u: string | URL, init?: RequestInit) => {
    const r = await yf.f(u, init);
    if (!/scoreboard;week=1/.test(String(u))) return r;
    const body = await r.json();
    body.fantasy_content.league[1].scoreboard["0"].matchups["0"].matchup.status = "preevent";
    return jsonRes(body);
  };
  const { summary } = await pullYahoo(f, "tok", yf.fx.lk);
  assertEquals(summary.schedule[0].matchups[0].points, [null, null]);
  assertEquals(summary.schedule[0].matchups[0].status, "not_started");
});

Deno.test("Yahoo 403 (app not approved yet) says so", async () => {
  const { fx, f } = yahooFetch(403);
  const e = await assertRejects(() => pullYahoo(f, "tok", fx.lk));
  assertEquals((e as { code: string }).code, "yahoo_app_not_approved");
});

// ---------- crypto ----------
Deno.test("tokens seal and open only with the same user and platform", async () => {
  const key = await importTokenKey(KEY_B64);
  const s = await seal(key, { access_token: "secret-access" }, "u:yahoo");
  assert(!new TextDecoder().decode(s.ciphertext).includes("secret-access"));
  assertEquals(await unseal(key, s, "u:yahoo"), { access_token: "secret-access" });
  await assertRejects(() => unseal(key, s, "other:yahoo"));
  await assertRejects(() => importTokenKey(btoa("short")));
});

// ---------- router ----------
function makeDeps(overrides: Partial<Deps> = {}) {
  const store = new MemoryStore();
  store.allow.add("me@example.com");
  const logs: string[] = [];
  const deleted: string[] = [];
  const users: Record<string, { id: string; email: string; email_confirmed: boolean }> = {
    "jwt-me": { id: "11111111-1111-4111-8111-111111111111", email: "me@example.com", email_confirmed: true },
    "jwt-other": { id: "22222222-2222-4222-8222-222222222222", email: "other@example.com", email_confirmed: true },
    "jwt-unconfirmed": { id: "33333333-3333-4333-8333-333333333333", email: "me@example.com", email_confirmed: false },
  };
  const deps: Deps = {
    store,
    fetch: async () => jsonRes(null, 404),
    authUser: async (jwt) => users[jwt] ?? null,
    deleteAuthUser: async (id) => { deleted.push(id); },
    tokenKey: () => importTokenKey(KEY_B64),
    env: (k) => ({ YAHOO_CLIENT_ID: "cid", YAHOO_CLIENT_SECRET: "csecret" } as Record<string, string>)[k],
    functionsBase: "https://ref.supabase.co/functions/v1",
    allowedOrigins: ["https://datadrivenfootball.github.io"],
    now: () => new Date("2026-11-27T12:00:00Z"),
    log: (f) => logs.push(JSON.stringify(f)),
    ...overrides,
  };
  return { deps, store, logs, deleted, users };
}
const BASE = "https://ref.supabase.co/functions/v1/ddf-account";
const call = (h: (r: Request) => Promise<Response>, method: string, path: string, jwt?: string, body?: unknown, origin = "https://datadrivenfootball.github.io") =>
  h(new Request(BASE + path, {
    method,
    headers: { ...(jwt ? { authorization: "Bearer " + jwt } : {}), "content-type": "application/json", origin },
    body: body === undefined ? undefined : JSON.stringify(body),
  }));

Deno.test("signed out is 401, a user not on the allowlist is 403", async () => {
  const { deps } = makeDeps();
  const h = makeApp(deps);
  assertEquals((await call(h, "GET", "/me")).status, 401);
  assertEquals((await call(h, "GET", "/me", "jwt-other")).status, 403);
  assertEquals((await call(h, "GET", "/me", "jwt-unconfirmed")).status, 403); // allowlisted address, not confirmed
  assertEquals((await call(h, "GET", "/leagues/not-a-uuid", "jwt-me")).status, 404); // never a 500 from Postgres
  const ok = await call(h, "GET", "/me", "jwt-me");
  assertEquals(ok.status, 200);
  assertEquals(ok.headers.get("access-control-allow-origin"), "https://datadrivenfootball.github.io");
  const elsewhere = await call(h, "GET", "/me", "jwt-me", undefined, "https://evil.example");
  assertEquals(elsewhere.headers.get("access-control-allow-origin"), null);
});

Deno.test("Sleeper end to end: connect, pull, pick team, confirm, refresh, disconnect, delete account", async () => {
  const { fetch } = await sleeperFetch();
  const { deps, store, deleted, logs } = makeDeps({ fetch });
  const h = makeApp(deps);
  const con = await (await call(h, "POST", "/sleeper/connect", "jwt-me", { username: "manager_1" })).json();
  assertEquals(con.leagues.length, 1);
  const pulled = await call(h, "POST", "/leagues", "jwt-me", { connection_id: con.connection.id, league_key: con.leagues[0].league_key });
  assertEquals(pulled.status, 200);
  const { league } = await pulled.json();
  assertEquals(league.raw, undefined);
  assertEquals(league.summary.teams.length, 12);
  assertEquals((await call(h, "POST", `/leagues/${league.id}/team`, "jwt-me", { team_key: "nope" })).status, 400);
  assertEquals((await (await call(h, "POST", `/leagues/${league.id}/team`, "jwt-me", { team_key: "3" })).json()).league.my_team_key, "3");
  assertEquals((await call(h, "POST", `/leagues/${league.id}/confirm`, "jwt-me", { settings: { scoring: "ppr", superflex: true, teams: 11 } })).status, 400);
  const conf = await (await call(h, "POST", `/leagues/${league.id}/confirm`, "jwt-me", { settings: league.summary.settings.ddf })).json();
  assertEquals(conf.league.confirmed_settings, league.summary.settings.ddf);
  // refresh keeps the chosen team
  const ref = await (await call(h, "POST", `/leagues/${league.id}/refresh`, "jwt-me")).json();
  assertEquals(ref.league.my_team_key, "3");
  // another allowlisted user cannot read it
  store.allow.add("other@example.com");
  assertEquals((await call(h, "GET", `/leagues/${league.id}`, "jwt-other")).status, 404);
  // disconnect removes its leagues
  assertEquals((await call(h, "DELETE", `/connections/${con.connection.id}`, "jwt-me")).status, 200);
  assertEquals(store.lgs.length, 0);
  assertEquals((await call(h, "DELETE", "/account", "jwt-me")).status, 200);
  assertEquals(deleted, ["11111111-1111-4111-8111-111111111111"]);
  assert(logs.every((l) => !l.includes("me@example.com")));
});

Deno.test("Yahoo OAuth: state is single-use, tokens are sealed, nothing secret is logged", async () => {
  const yf = yahooFetch();
  const f = async (u: string | URL, init?: RequestInit) => {
    if (String(u).includes("get_token")) {
      assertEquals(new Headers(init?.headers).get("authorization"), "Basic " + btoa("cid:csecret"));
      return jsonRes({ access_token: "ACCESS-123", refresh_token: "REFRESH-456", expires_in: 3600, xoauth_yahoo_guid: "GUID1" });
    }
    return yf.f(u, init);
  };
  const { deps, store, logs } = makeDeps({ fetch: f });
  const h = makeApp(deps);
  assertEquals((await call(h, "POST", "/yahoo/start", "jwt-me", { return_to: "https://evil.example/x" })).status, 400);
  const { url } = await (await call(h, "POST", "/yahoo/start", "jwt-me", { return_to: "https://datadrivenfootball.github.io/ddf-staging/" })).json();
  const auth = new URL(url);
  assertEquals(auth.searchParams.get("redirect_uri"), "https://ref.supabase.co/functions/v1/ddf-account/yahoo/callback");
  const state = auth.searchParams.get("state")!;
  const cb = await h(new Request(`${BASE}/yahoo/callback?code=CODE-1&state=${state}`));
  assertEquals(cb.status, 302);
  const loc = cb.headers.get("location")!;
  assert(loc.startsWith("https://datadrivenfootball.github.io/ddf-staging/#yahoo=finish&h="));
  const handoff = new URLSearchParams(loc.split("#")[1]).get("h")!;
  assertEquals((await h(new Request(`${BASE}/yahoo/callback?code=CODE-1&state=${state}`))).status, 400); // state is single-use
  // The callback attached nothing: tokens wait for the same signed-in DDF user.
  assertEquals(store.conns.length, 0);
  store.allow.add("other@example.com");
  assertEquals((await call(h, "POST", "/yahoo/finish", "jwt-other", { handoff })).status, 403);
  assertEquals(store.conns.length, 0);
  // That attempt consumed the handoff, so a fresh start is needed.
  assertEquals((await call(h, "POST", "/yahoo/finish", "jwt-me", { handoff })).status, 400);
  const again = new URL((await (await call(h, "POST", "/yahoo/start", "jwt-me", { return_to: "https://datadrivenfootball.github.io/ddf-staging/" })).json()).url).searchParams.get("state")!;
  const cb2 = await h(new Request(`${BASE}/yahoo/callback?code=CODE-1&state=${again}`));
  const handoff2 = new URLSearchParams(cb2.headers.get("location")!.split("#")[1]).get("h")!;
  assertEquals((await call(h, "POST", "/yahoo/finish", "jwt-me", { handoff: handoff2 })).status, 200);
  const conn = store.conns[0];
  assertEquals([conn.platform, conn.external_id], ["yahoo", "GUID1"]);
  const stored = new TextDecoder().decode(conn.secret_ciphertext!);
  assert(!stored.includes("ACCESS-123") && !stored.includes("REFRESH-456"));
  const me = await (await call(h, "GET", "/me", "jwt-me")).json();
  assertEquals(me.connections[0].has_secret, true);
  assertEquals(JSON.stringify(me).includes("secret_ciphertext"), false);
  const pulled = await (await call(h, "POST", "/leagues", "jwt-me", { connection_id: conn.id, league_key: yf.fx.lk })).json();
  assertEquals(pulled.league.my_team_key, yf.fx.lk + ".t.2");
  assert(yf.seen.every((s) => s.auth === "Bearer ACCESS-123"));
  assert(logs.every((l) => !/ACCESS-123|REFRESH-456|CODE-1|csecret/.test(l) && !l.includes(state) && !l.includes(handoff2)));
});

Deno.test("expired Yahoo tokens refresh and are re-sealed", async () => {
  let refreshed = 0;
  const yf = yahooFetch();
  const f = async (u: string | URL, init?: RequestInit) => {
    if (String(u).includes("get_token")) {
      refreshed++;
      assert(String(init?.body).includes("grant_type=refresh_token"));
      return jsonRes({ access_token: "NEW", expires_in: 3600 });
    }
    return yf.f(u, init);
  };
  const { deps, store } = makeDeps({ fetch: f });
  const key = await importTokenKey(KEY_B64);
  const uid = "11111111-1111-4111-8111-111111111111";
  const s = await seal(key, { access_token: "OLD", refresh_token: "R", expires_at: Date.parse("2026-11-27T11:00:00Z"), guid: "G" }, `${uid}:yahoo`);
  const conn = await store.upsertConnection({ user_id: uid, platform: "yahoo", external_id: "G", display_name: "Yahoo", secret_ciphertext: s.ciphertext, secret_iv: s.iv, token_expires_at: null });
  const h = makeApp(deps);
  assertEquals((await call(h, "POST", "/leagues", "jwt-me", { connection_id: conn.id, league_key: yf.fx.lk })).status, 200);
  assertEquals(refreshed, 1);
  const t = await unseal<{ access_token: string; refresh_token: string }>(key, { ciphertext: conn.secret_ciphertext!, iv: conn.secret_iv! }, `${uid}:yahoo`);
  assertEquals([t.access_token, t.refresh_token], ["NEW", "R"]);
  assert(yf.seen.every((x) => x.auth === "Bearer NEW"));
});

Deno.test("confirmed settings are checked", () => {
  assertEquals(validSettings({ scoring: "ppr", superflex: false, teams: 12 }), { scoring: "ppr", superflex: false, teams: 12 });
  for (const bad of [null, { scoring: "x", superflex: false }, { scoring: "ppr", superflex: "no" }, { scoring: "ppr", superflex: false, roster: { QB: -1 } }]) {
    let threw = false;
    try { validSettings(bad); } catch { threw = true; }
    assert(threw, JSON.stringify(bad));
  }
});

Deno.test("ESPN: a private league is refused before anything is stored", async () => {
  const { deps, store } = makeDeps({ fetch: async () => jsonRes({}, 401) });
  const h = makeApp(deps);
  const r = await call(h, "POST", "/espn/connect", "jwt-me", { league_id: "https://fantasy.espn.com/football/league?leagueId=123456&seasonId=2026" });
  assertEquals(r.status, 403);
  assertEquals((await r.json()).error.code, "espn_private");
  assertEquals(store.conns.length, 0);
});

Deno.test("ESPN private league: session keys are checked, sent as cookies, sealed at rest, reused on pull", async () => {
  const s = await fixture("tests/fixtures/espn/settings.json");
  const t = await fixture("tests/fixtures/espn/teams.json");
  const lg = { ...s, ...t, settings: s.settings };
  const S2 = "AEB" + "x".repeat(120);
  const SWID = "{1A2B3C4D-1111-2222-3333-444455556666}";
  const cookies: (string | null)[] = [];
  const f = async (_u: string | URL, init?: RequestInit) => {
    const c = new Headers(init?.headers).get("cookie");
    cookies.push(c);
    return c === `espn_s2=${S2}; SWID=${SWID}` ? jsonRes(lg) : jsonRes({}, 401);
  };
  const { deps, store, logs } = makeDeps({ fetch: f });
  const h = makeApp(deps);
  const noKeys = await call(h, "POST", "/espn/connect", "jwt-me", { league_id: "123456" });
  assertEquals((await noKeys.json()).error.code, "espn_private");
  assertEquals((await call(h, "POST", "/espn/connect", "jwt-me", { league_id: "123456", espn_s2: S2, swid: "not-a-guid" })).status, 400);
  const wrong = await call(h, "POST", "/espn/connect", "jwt-me", { league_id: "123456", espn_s2: "B" + S2, swid: SWID });
  assertEquals((await wrong.json()).error.code, "espn_session_rejected");
  assertEquals(store.conns.length, 0);
  // SWID without braces is accepted and normalized
  const ok = await (await call(h, "POST", "/espn/connect", "jwt-me", { league_id: "https://fantasy.espn.com/football/league?leagueId=123456", espn_s2: S2, swid: SWID.slice(1, -1).toLowerCase() })).json();
  assertEquals(ok.season, 2026); // always the current season
  const conn = store.conns[0];
  assert(!new TextDecoder().decode(conn.secret_ciphertext!).includes(S2));
  const pulled = await call(h, "POST", "/leagues", "jwt-me", { connection_id: conn.id, league_key: "123456" });
  assertEquals(pulled.status, 200);
  assertEquals(cookies.at(-1), `espn_s2=${S2}; SWID=${SWID}`);
  assert(logs.every((l) => !l.includes(S2) && !l.includes("1A2B3C4D")));
  const me = await (await call(h, "GET", "/me", "jwt-me")).json();
  assert(!JSON.stringify(me).includes(S2));
});
