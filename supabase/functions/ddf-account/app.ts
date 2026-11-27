// ddf-account router (JEG-1732): DDF sign-in (Supabase Auth) plus read-only league
// connections for Sleeper, Yahoo and ESPN, private staging only.
//
// Every route but the Yahoo callback needs a Supabase user JWT, and the user's email
// must be on ddf_accounts.allowlist. Logs carry the route, status, time and error code
// only: never a body, a token, a cookie or an email.
import { randomToken, seal, unseal } from "./crypto.ts";
import { AppError, Fetch } from "./errors.ts";
import { parseEspnLeagueId, espnSeasonNow, readEspnLeague, summarizeEspn } from "./espn.ts";
import { pullSleeper, sleeperLeagues, sleeperPlayerIndex, sleeperUser } from "./sleeper.ts";
import { SIZES, type DdfSettings } from "./shape.ts";
import { type Connection, publicConnection, type Store } from "./store.ts";
import { authorizeUrl, exchangeCode, pullYahoo, refreshTokens, yahooConfig, yahooLeagues, type YahooTokens } from "./yahoo.ts";

export type AuthUser = { id: string; email: string | null };
export type Deps = {
  store: Store;
  fetch: Fetch;
  authUser: (jwt: string) => Promise<AuthUser | null>;
  deleteAuthUser: (id: string) => Promise<void>;
  tokenKey: () => Promise<CryptoKey>;
  env: (k: string) => string | undefined;
  functionsBase: string; // https://<ref>.supabase.co/functions/v1
  allowedOrigins: string[];
  now: () => Date;
  log: (fields: Record<string, unknown>) => void;
};

const SLEEPER_CACHE = "sleeper_players_v1";
const DAY = 86400000;

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

function corsHeaders(req: Request, allowed: string[]) {
  const origin = req.headers.get("origin") || "";
  if (!allowed.includes(origin)) return {} as Record<string, string>;
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-headers": "authorization, content-type, apikey, x-client-info",
    "access-control-allow-methods": "GET, POST, DELETE, OPTIONS",
    "access-control-max-age": "600",
    vary: "origin",
  };
}

async function body<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    throw new AppError(400, "bad_json", "The request body is not JSON.");
  }
}

const aad = (c: Pick<Connection, "user_id" | "platform">) => `${c.user_id}:${c.platform}`;

export function validSettings(s: unknown): DdfSettings {
  const bad = (why: string): never => {
    throw new AppError(400, "bad_settings", `Settings not saved: ${why}.`);
  };
  if (!s || typeof s !== "object") bad("no settings");
  const x = s as Record<string, unknown>;
  if (!["ppr", "half_ppr", "standard"].includes(String(x.scoring))) bad("scoring must be ppr, half_ppr or standard");
  if (typeof x.superflex !== "boolean") bad("superflex must be true or false");
  if (x.teams !== undefined && !SIZES.includes(Number(x.teams))) bad("teams must be 8, 10, 12 or 14");
  if (x.superflexSlots !== undefined && ![1, 2].includes(Number(x.superflexSlots))) bad("superflexSlots must be 1 or 2");
  const out: DdfSettings = { scoring: x.scoring as DdfSettings["scoring"], superflex: x.superflex as boolean };
  if (x.teams !== undefined) out.teams = Number(x.teams);
  if (x.superflexSlots !== undefined) out.superflexSlots = Number(x.superflexSlots);
  if (x.roster !== undefined) {
    const r = x.roster as Record<string, unknown>;
    const keys = ["QB", "RB", "WR", "TE", "FLEX", "BENCH", "K", "DST"] as const;
    const roster = {} as NonNullable<DdfSettings["roster"]>;
    for (const k of keys) {
      const v = Number(r?.[k]);
      const hi = k === "K" || k === "DST" ? 3 : 20;
      if (!Number.isInteger(v) || v < 0 || v > hi) bad(`roster.${k} must be a whole number 0-${hi}`);
      roster[k] = v;
    }
    out.roster = roster;
  }
  return out;
}

export function makeApp(d: Deps) {
  async function yahooToken(conn: Connection): Promise<string> {
    const cfg = yahooConfig(d.env, d.functionsBase);
    if (!cfg) throw new AppError(503, "yahoo_not_configured", "Yahoo is not set up yet: the DDF Yahoo app keys are not in Supabase secrets.");
    if (!conn.secret_ciphertext || !conn.secret_iv) throw new AppError(409, "yahoo_no_token", "Connect Yahoo again.");
    const key = await d.tokenKey();
    let t = await unseal<YahooTokens>(key, { ciphertext: conn.secret_ciphertext, iv: conn.secret_iv }, aad(conn));
    if (t.expires_at - 60000 < d.now().getTime()) {
      t = await refreshTokens(d.fetch, cfg, t, d.now().getTime());
      const s = await seal(key, t, aad(conn));
      await d.store.setSecret(conn.id, s.ciphertext, s.iv, new Date(t.expires_at).toISOString());
    }
    return t.access_token;
  }

  async function sleeperNames(ids: string[]) {
    let cached = await d.store.cacheGet(SLEEPER_CACHE);
    if (!cached || d.now().getTime() - Date.parse(cached.fetched_at) > DAY) {
      const fresh = await sleeperPlayerIndex(d.fetch).catch(() => null);
      if (fresh) {
        await d.store.cachePut(SLEEPER_CACHE, fresh);
        cached = { body: fresh, fetched_at: d.now().toISOString() };
      }
    }
    const all = (cached?.body || {}) as Record<string, { n: string; p: string | null; t: string | null }>;
    return Object.fromEntries(ids.filter((id) => all[id]).map((id) => [id, all[id]]));
  }

  async function pull(user: AuthUser, conn: Connection, leagueKey: string, season?: number) {
    let summary, raw;
    if (conn.platform === "sleeper") {
      ({ summary, raw } = await pullSleeper(d.fetch, leagueKey, conn.external_id, sleeperNames, d.now()));
    } else if (conn.platform === "espn") {
      const yr = season ?? espnSeasonNow(d.now());
      raw = await readEspnLeague(d.fetch, conn.external_id, yr);
      summary = summarizeEspn(raw, conn.external_id, yr, d.now());
    } else {
      ({ summary, raw } = await pullYahoo(d.fetch, await yahooToken(conn), leagueKey, d.now()));
    }
    const row = await d.store.upsertLeague({
      user_id: user.id, connection_id: conn.id, platform: conn.platform, league_key: summary.league_key,
      season: summary.season, name: summary.name, my_team_key: summary.my_team_key, summary, raw, pulled_at: summary.pulled_at,
    });
    const { raw: _r, ...rest } = row;
    return rest;
  }

  async function route(req: Request, user: AuthUser, parts: string[]): Promise<Response> {
    const [a, b, c] = parts;
    const m = req.method;
    if (m === "GET" && a === "me") {
      const conns = await d.store.connections(user.id);
      return json({
        user: { id: user.id, email: user.email },
        connections: conns.map(publicConnection),
        leagues: await d.store.leagues(user.id),
        yahoo_configured: yahooConfig(d.env, d.functionsBase) !== null,
      });
    }
    if (m === "POST" && a === "sleeper" && b === "connect") {
      const { username } = await body<{ username: string }>(req);
      const su = await sleeperUser(d.fetch, username);
      const conn = await d.store.upsertConnection({ user_id: user.id, platform: "sleeper", external_id: su.user_id, display_name: su.display_name, secret_ciphertext: null, secret_iv: null, token_expires_at: null });
      return json({ connection: publicConnection(conn), ...(await sleeperLeagues(d.fetch, su.user_id)) });
    }
    if (m === "POST" && a === "espn" && b === "connect") {
      const { league_id, season } = await body<{ league_id: string; season?: number }>(req);
      const parsed = parseEspnLeagueId(String(league_id ?? ""));
      if (!parsed) throw new AppError(400, "invalid_league", "Paste your ESPN league link, or the number after leagueId=.");
      const yr = Number(season) || parsed.season || espnSeasonNow(d.now());
      const lg = await readEspnLeague(d.fetch, parsed.id, yr); // public check before storing anything
      const conn = await d.store.upsertConnection({ user_id: user.id, platform: "espn", external_id: parsed.id, display_name: String(lg?.settings?.name || `ESPN ${parsed.id}`).slice(0, 80), secret_ciphertext: null, secret_iv: null, token_expires_at: null });
      return json({ connection: publicConnection(conn), season: yr, leagues: [{ league_key: parsed.id, name: conn.display_name, season: yr, teams: lg?.settings?.size ?? null }] });
    }
    if (m === "POST" && a === "yahoo" && b === "start") {
      const cfg = yahooConfig(d.env, d.functionsBase);
      if (!cfg) throw new AppError(503, "yahoo_not_configured", "Yahoo is not set up yet: the DDF Yahoo app keys are not in Supabase secrets.");
      const { return_to } = await body<{ return_to: string }>(req);
      const back = String(return_to || "");
      if (!d.allowedOrigins.some((o) => back === o || back.startsWith(o + "/"))) throw new AppError(400, "bad_return_to", "return_to must be the staging page.");
      const state = randomToken();
      await d.store.putState(state, user.id, "yahoo", back);
      return json({ url: authorizeUrl(cfg, state) });
    }
    if (a === "connections" && b) {
      const conn = await d.store.connection(user.id, b);
      if (!conn) throw new AppError(404, "not_found", "That connection is not on your account.");
      if (m === "DELETE" && !c) {
        await d.store.deleteConnection(user.id, b);
        return json({ deleted: true });
      }
      if (m === "GET" && c === "leagues") {
        if (conn.platform === "sleeper") return json(await sleeperLeagues(d.fetch, conn.external_id));
        if (conn.platform === "yahoo") return json(await yahooLeagues(d.fetch, await yahooToken(conn)));
        return json({ leagues: [{ league_key: conn.external_id, name: conn.display_name }] });
      }
    }
    if (a === "leagues") {
      if (m === "POST" && !b) {
        const { connection_id, league_key, season } = await body<{ connection_id: string; league_key: string; season?: number }>(req);
        const conn = await d.store.connection(user.id, String(connection_id));
        if (!conn) throw new AppError(404, "not_found", "That connection is not on your account.");
        return json({ league: await pull(user, conn, String(league_key), season ? Number(season) : undefined) });
      }
      if (b) {
        const lg = await d.store.league(user.id, b);
        if (!lg) throw new AppError(404, "not_found", "That league is not on your account.");
        if (m === "GET" && !c) {
          const url = new URL(req.url);
          if (url.searchParams.get("raw") === "1") return json({ league: lg });
          const { raw: _r, ...rest } = lg;
          return json({ league: rest });
        }
        if (m === "DELETE" && !c) return json({ deleted: await d.store.deleteLeague(user.id, b) });
        if (m === "POST" && c === "refresh") {
          const conn = await d.store.connection(user.id, lg.connection_id);
          if (!conn) throw new AppError(404, "not_found", "That league's connection is gone.");
          return json({ league: await pull(user, conn, lg.league_key, lg.season) });
        }
        if (m === "POST" && c === "team") {
          const { team_key } = await body<{ team_key: string }>(req);
          const teams = ((lg.summary as { teams?: { team_key: string }[] })?.teams || []).map((t) => t.team_key);
          if (!teams.includes(String(team_key))) throw new AppError(400, "bad_team", "That team is not in this league.");
          const { raw: _r, ...rest } = (await d.store.updateLeague(user.id, b, { my_team_key: String(team_key) }))!;
          return json({ league: rest });
        }
        if (m === "POST" && c === "confirm") {
          const { settings } = await body<{ settings: unknown }>(req);
          const { raw: _r, ...rest } = (await d.store.updateLeague(user.id, b, { confirmed_settings: validSettings(settings), confirmed_at: d.now().toISOString() }))!;
          return json({ league: rest });
        }
      }
    }
    if (m === "DELETE" && a === "account") {
      await d.store.deleteUserData(user.id);
      await d.deleteAuthUser(user.id);
      return json({ deleted: true });
    }
    throw new AppError(404, "no_route", "Unknown request.");
  }

  async function yahooCallback(url: URL): Promise<Response> {
    const state = url.searchParams.get("state") || "";
    const st = state ? await d.store.takeState(state) : null;
    if (!st) return new Response("This Yahoo sign-in link expired. Go back to DDF and press Connect Yahoo again.", { status: 400 });
    const back = (code: string, ok: boolean) =>
      new Response(null, { status: 302, headers: { location: `${st.return_to}#yahoo=${ok ? "connected" : "error"}${ok ? "" : "&code=" + code}` } });
    const code = url.searchParams.get("code");
    if (!code) return back(String(url.searchParams.get("error") || "denied").replace(/[^a-z_]/gi, "").slice(0, 40), false);
    const cfg = yahooConfig(d.env, d.functionsBase);
    if (!cfg) return back("yahoo_not_configured", false);
    try {
      const t = await exchangeCode(d.fetch, cfg, code, d.now().getTime());
      const key = await d.tokenKey();
      const owner = { user_id: st.user_id, platform: "yahoo" as const };
      const s = await seal(key, t, aad(owner));
      await d.store.upsertConnection({ ...owner, external_id: t.guid || "yahoo", display_name: "Yahoo", secret_ciphertext: s.ciphertext, secret_iv: s.iv, token_expires_at: new Date(t.expires_at).toISOString() });
      return back("", true);
    } catch (e) {
      return back(e instanceof AppError ? e.code : "error", false);
    }
  }

  return async function handle(req: Request): Promise<Response> {
    const t0 = Date.now();
    const url = new URL(req.url);
    const parts = url.pathname.split("/").filter(Boolean);
    const at = parts.indexOf("ddf-account");
    const rest = at >= 0 ? parts.slice(at + 1) : parts;
    const routeName = `${req.method} /${rest.map((p) => (/^[0-9a-f-]{36}$/.test(p) ? ":id" : p)).join("/")}`;
    const cors = corsHeaders(req, d.allowedOrigins);
    let res: Response, code: string | null = null;
    try {
      if (req.method === "OPTIONS") res = new Response(null, { status: 204, headers: cors });
      else if (req.method === "GET" && rest[0] === "yahoo" && rest[1] === "callback") res = await yahooCallback(url);
      else {
        const jwt = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
        const user = jwt ? await d.authUser(jwt) : null;
        if (!user) throw new AppError(401, "signed_out", "Sign in to DDF first.");
        if (!user.email || !(await d.store.isAllowed(user.email))) throw new AppError(403, "not_allowlisted", "This staging build is limited to invited accounts.");
        res = await route(req, user, rest);
      }
    } catch (e) {
      const err = e instanceof AppError ? e : new AppError(500, "internal", "Something went wrong on DDF's side. Try again.");
      code = err.code;
      res = json({ error: { code: err.code, message: err.message } }, err.status);
    }
    for (const [k, v] of Object.entries(cors)) res.headers.set(k, v);
    d.log({ fn: "ddf-account", route: routeName, status: res.status, ms: Date.now() - t0, code });
    return res;
  };
}
