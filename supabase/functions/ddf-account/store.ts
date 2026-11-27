// deno-lint-ignore-file require-await -- the Store interface is async; the in-memory and stub versions have nothing to await
// Storage for ddf_accounts (JEG-1732). PgStore talks to Postgres directly (the
// schema is not exposed to PostgREST); MemoryStore backs the tests.
import type { Platform } from "./shape.ts";

export type Connection = {
  id: string;
  user_id: string;
  platform: Platform;
  external_id: string;
  display_name: string | null;
  secret_ciphertext: Uint8Array | null;
  secret_iv: Uint8Array | null;
  token_expires_at: string | null;
  created_at: string;
  updated_at: string;
};
export type PublicConnection = Omit<Connection, "secret_ciphertext" | "secret_iv" | "user_id"> & { has_secret: boolean };

export type League = {
  id: string;
  user_id: string;
  connection_id: string;
  platform: Platform;
  league_key: string;
  season: number;
  name: string | null;
  my_team_key: string | null;
  summary: unknown;
  raw: unknown;
  confirmed_settings: unknown;
  confirmed_at: string | null;
  pulled_at: string;
};

export type Handoff = {
  id: string;
  user_id: string;
  platform: "yahoo";
  external_id: string;
  secret_ciphertext: Uint8Array;
  secret_iv: Uint8Array;
  token_expires_at: string | null;
};

export interface Store {
  isAllowed(email: string): Promise<boolean>;
  connections(userId: string): Promise<Connection[]>;
  connection(userId: string, id: string): Promise<Connection | null>;
  upsertConnection(c: Pick<Connection, "user_id" | "platform" | "external_id" | "display_name" | "secret_ciphertext" | "secret_iv" | "token_expires_at">): Promise<Connection>;
  setSecret(id: string, ct: Uint8Array, iv: Uint8Array, expires: string | null): Promise<void>;
  deleteConnection(userId: string, id: string): Promise<boolean>;
  putState(state: string, userId: string, platform: "yahoo", returnTo: string): Promise<void>;
  takeState(state: string): Promise<{ user_id: string; platform: string; return_to: string } | null>;
  putHandoff(h: Handoff): Promise<void>;
  takeHandoff(id: string): Promise<Handoff | null>;
  upsertLeague(l: Omit<League, "id" | "confirmed_settings" | "confirmed_at">): Promise<League>;
  leagues(userId: string): Promise<Omit<League, "raw" | "summary">[]>;
  league(userId: string, id: string): Promise<League | null>;
  updateLeague(userId: string, id: string, patch: Partial<Pick<League, "my_team_key" | "confirmed_settings" | "confirmed_at">>): Promise<League | null>;
  deleteLeague(userId: string, id: string): Promise<boolean>;
  deleteUserData(userId: string): Promise<void>;
  cacheGet(key: string): Promise<{ body: unknown; fetched_at: string } | null>;
  cachePut(key: string, body: unknown): Promise<void>;
}

export function publicConnection(c: Connection): PublicConnection {
  const { secret_ciphertext, secret_iv: _iv, user_id: _u, ...rest } = c;
  return { ...rest, has_secret: secret_ciphertext !== null };
}

// deno-lint-ignore no-explicit-any
type Sql = any;

const u8 = (b: unknown) => (b == null ? null : new Uint8Array(b as ArrayBuffer));
function rowConn(r: Record<string, unknown>): Connection {
  return { ...(r as unknown as Connection), secret_ciphertext: u8(r.secret_ciphertext), secret_iv: u8(r.secret_iv) };
}

export class PgStore implements Store {
  constructor(private sql: Sql) {}
  async isAllowed(email: string) {
    const r = await this.sql`select 1 from ddf_accounts.allowlist where email = ${email.toLowerCase()}`;
    return r.length > 0;
  }
  async connections(userId: string) {
    return (await this.sql`select * from ddf_accounts.connections where user_id = ${userId} order by created_at`).map(rowConn);
  }
  async connection(userId: string, id: string) {
    const r = await this.sql`select * from ddf_accounts.connections where user_id = ${userId} and id = ${id}`;
    return r[0] ? rowConn(r[0]) : null;
  }
  async upsertConnection(c: Parameters<Store["upsertConnection"]>[0]) {
    const r = await this.sql`
      insert into ddf_accounts.connections (user_id, platform, external_id, display_name, secret_ciphertext, secret_iv, token_expires_at)
      values (${c.user_id}, ${c.platform}, ${c.external_id}, ${c.display_name}, ${c.secret_ciphertext}, ${c.secret_iv}, ${c.token_expires_at})
      on conflict (user_id, platform, external_id) do update set
        display_name = excluded.display_name, secret_ciphertext = excluded.secret_ciphertext,
        secret_iv = excluded.secret_iv, token_expires_at = excluded.token_expires_at, updated_at = now()
      returning *`;
    return rowConn(r[0]);
  }
  async setSecret(id: string, ct: Uint8Array, iv: Uint8Array, expires: string | null) {
    await this.sql`update ddf_accounts.connections set secret_ciphertext = ${ct}, secret_iv = ${iv}, token_expires_at = ${expires}, updated_at = now() where id = ${id}`;
  }
  async deleteConnection(userId: string, id: string) {
    return (await this.sql`delete from ddf_accounts.connections where user_id = ${userId} and id = ${id} returning id`).length > 0;
  }
  async putState(state: string, userId: string, platform: "yahoo", returnTo: string) {
    await this.sql`delete from ddf_accounts.oauth_states where expires_at < now()`;
    await this.sql`insert into ddf_accounts.oauth_states (state, user_id, platform, return_to) values (${state}, ${userId}, ${platform}, ${returnTo})`;
  }
  async takeState(state: string) {
    const r = await this.sql`delete from ddf_accounts.oauth_states where state = ${state} and expires_at > now() returning user_id, platform, return_to`;
    return r[0] ?? null;
  }
  async putHandoff(h: Handoff) {
    await this.sql`delete from ddf_accounts.oauth_handoffs where expires_at < now()`;
    await this.sql`insert into ddf_accounts.oauth_handoffs (id, user_id, platform, external_id, secret_ciphertext, secret_iv, token_expires_at)
      values (${h.id}, ${h.user_id}, ${h.platform}, ${h.external_id}, ${h.secret_ciphertext}, ${h.secret_iv}, ${h.token_expires_at})`;
  }
  async takeHandoff(id: string) {
    const r = await this.sql`delete from ddf_accounts.oauth_handoffs where id = ${id} and expires_at > now() returning *`;
    return r[0] ? { ...r[0], secret_ciphertext: u8(r[0].secret_ciphertext)!, secret_iv: u8(r[0].secret_iv)! } as Handoff : null;
  }
  async upsertLeague(l: Parameters<Store["upsertLeague"]>[0]) {
    const r = await this.sql`
      insert into ddf_accounts.leagues (user_id, connection_id, platform, league_key, season, name, my_team_key, summary, raw, pulled_at)
      values (${l.user_id}, ${l.connection_id}, ${l.platform}, ${l.league_key}, ${l.season}, ${l.name}, ${l.my_team_key},
              ${this.sql.json(l.summary)}, ${this.sql.json(l.raw)}, ${l.pulled_at})
      on conflict (user_id, platform, league_key) do update set
        connection_id = excluded.connection_id, season = excluded.season, name = excluded.name,
        my_team_key = coalesce(ddf_accounts.leagues.my_team_key, excluded.my_team_key),
        summary = excluded.summary, raw = excluded.raw, pulled_at = excluded.pulled_at
      returning *`;
    return r[0];
  }
  async leagues(userId: string) {
    return await this.sql`select id, user_id, connection_id, platform, league_key, season, name, my_team_key, confirmed_settings, confirmed_at, pulled_at
      from ddf_accounts.leagues where user_id = ${userId} order by pulled_at desc`;
  }
  async league(userId: string, id: string) {
    return (await this.sql`select * from ddf_accounts.leagues where user_id = ${userId} and id = ${id}`)[0] ?? null;
  }
  async updateLeague(userId: string, id: string, patch: Parameters<Store["updateLeague"]>[2]) {
    const cur = await this.league(userId, id);
    if (!cur) return null;
    const n = { ...cur, ...patch };
    const r = await this.sql`update ddf_accounts.leagues set my_team_key = ${n.my_team_key},
      confirmed_settings = ${n.confirmed_settings === null ? null : this.sql.json(n.confirmed_settings)}, confirmed_at = ${n.confirmed_at}
      where user_id = ${userId} and id = ${id} returning *`;
    return r[0] ?? null;
  }
  async deleteLeague(userId: string, id: string) {
    return (await this.sql`delete from ddf_accounts.leagues where user_id = ${userId} and id = ${id} returning id`).length > 0;
  }
  async deleteUserData(userId: string) {
    await this.sql`delete from ddf_accounts.connections where user_id = ${userId}`;
    await this.sql`delete from ddf_accounts.oauth_states where user_id = ${userId}`;
    await this.sql`delete from ddf_accounts.oauth_handoffs where user_id = ${userId}`;
  }
  async cacheGet(key: string) {
    return (await this.sql`select body, fetched_at from ddf_accounts.platform_cache where key = ${key}`)[0] ?? null;
  }
  async cachePut(key: string, body: unknown) {
    await this.sql`insert into ddf_accounts.platform_cache (key, body, fetched_at) values (${key}, ${this.sql.json(body)}, now())
      on conflict (key) do update set body = excluded.body, fetched_at = now()`;
  }
}

export class MemoryStore implements Store {
  allow = new Set<string>();
  conns: Connection[] = [];
  states: { state: string; user_id: string; platform: string; return_to: string; expires: number }[] = [];
  lgs: League[] = [];
  handoffs: (Handoff & { expires: number })[] = [];
  cache = new Map<string, { body: unknown; fetched_at: string }>();
  private n = 0;
  private id() { return `00000000-0000-4000-8000-${String(++this.n).padStart(12, "0")}`; }
  async isAllowed(email: string) { return this.allow.has(email.toLowerCase()); }
  async connections(userId: string) { return this.conns.filter((c) => c.user_id === userId); }
  async connection(userId: string, id: string) { return this.conns.find((c) => c.user_id === userId && c.id === id) ?? null; }
  async upsertConnection(c: Parameters<Store["upsertConnection"]>[0]) {
    const now = new Date().toISOString();
    const cur = this.conns.find((x) => x.user_id === c.user_id && x.platform === c.platform && x.external_id === c.external_id);
    if (cur) { Object.assign(cur, c, { updated_at: now }); return cur; }
    const row = { ...c, id: this.id(), created_at: now, updated_at: now } as Connection;
    this.conns.push(row);
    return row;
  }
  async setSecret(id: string, ct: Uint8Array, iv: Uint8Array, expires: string | null) {
    const c = this.conns.find((x) => x.id === id);
    if (c) Object.assign(c, { secret_ciphertext: ct, secret_iv: iv, token_expires_at: expires });
  }
  async deleteConnection(userId: string, id: string) {
    const before = this.conns.length;
    this.conns = this.conns.filter((c) => !(c.user_id === userId && c.id === id));
    this.lgs = this.lgs.filter((l) => l.connection_id !== id);
    return this.conns.length < before;
  }
  async putState(state: string, userId: string, platform: "yahoo", returnTo: string) {
    this.states.push({ state, user_id: userId, platform, return_to: returnTo, expires: Date.now() + 600000 });
  }
  async takeState(state: string) {
    const i = this.states.findIndex((s) => s.state === state && s.expires > Date.now());
    if (i < 0) return null;
    const [s] = this.states.splice(i, 1);
    return s;
  }
  async putHandoff(h: Handoff) { this.handoffs.push({ ...h, expires: Date.now() + 600000 }); }
  async takeHandoff(id: string) {
    const i = this.handoffs.findIndex((h) => h.id === id && h.expires > Date.now());
    if (i < 0) return null;
    const [{ expires: _e, ...h }] = this.handoffs.splice(i, 1);
    return h;
  }
  async upsertLeague(l: Parameters<Store["upsertLeague"]>[0]) {
    const cur = this.lgs.find((x) => x.user_id === l.user_id && x.platform === l.platform && x.league_key === l.league_key);
    if (cur) { Object.assign(cur, { ...l, my_team_key: cur.my_team_key ?? l.my_team_key }); return cur; }
    const row = { ...l, id: this.id(), confirmed_settings: null, confirmed_at: null } as League;
    this.lgs.push(row);
    return row;
  }
  async leagues(userId: string) {
    return this.lgs.filter((l) => l.user_id === userId).map(({ raw: _r, summary: _s, ...rest }) => rest);
  }
  async league(userId: string, id: string) { return this.lgs.find((l) => l.user_id === userId && l.id === id) ?? null; }
  async updateLeague(userId: string, id: string, patch: Parameters<Store["updateLeague"]>[2]) {
    const l = await this.league(userId, id);
    if (l) Object.assign(l, patch);
    return l;
  }
  async deleteLeague(userId: string, id: string) {
    const before = this.lgs.length;
    this.lgs = this.lgs.filter((l) => !(l.user_id === userId && l.id === id));
    return this.lgs.length < before;
  }
  async deleteUserData(userId: string) {
    const ids = new Set(this.conns.filter((c) => c.user_id === userId).map((c) => c.id));
    this.conns = this.conns.filter((c) => c.user_id !== userId);
    this.lgs = this.lgs.filter((l) => !ids.has(l.connection_id));
    this.states = this.states.filter((s) => s.user_id !== userId);
    this.handoffs = this.handoffs.filter((h) => h.user_id !== userId);
  }
  async cacheGet(key: string) { return this.cache.get(key) ?? null; }
  async cachePut(key: string, body: unknown) { this.cache.set(key, { body, fetched_at: new Date().toISOString() }); }
}
