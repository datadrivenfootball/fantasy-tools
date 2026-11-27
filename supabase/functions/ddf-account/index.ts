// ddf-account edge function entrypoint (JEG-1732). Deploy with JWT verification off:
// the function checks the Supabase user JWT itself, and the Yahoo callback has none.
//   supabase functions deploy ddf-account --no-verify-jwt --project-ref iskiybsimubiujwuchsl
// Secrets (supabase secrets set, never in files): DDF_TOKEN_KEY (32 bytes base64),
// YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET; optional YAHOO_SCOPE, YAHOO_REDIRECT_URI,
// DDF_STAGING_ORIGINS (comma list, default https://datadrivenfootball.github.io).
import postgres from "npm:postgres@3.4.5";
import { createClient } from "npm:@supabase/supabase-js@2.49.4";
import { makeApp } from "./app.ts";
import { importTokenKey } from "./crypto.ts";
import { PgStore } from "./store.ts";

const env = (k: string) => Deno.env.get(k);
const SUPABASE_URL = env("SUPABASE_URL")!;
const admin = createClient(SUPABASE_URL, env("SUPABASE_SERVICE_ROLE_KEY")!, { auth: { persistSession: false, autoRefreshToken: false } });
const sql = postgres(env("SUPABASE_DB_URL")!, { prepare: false, max: 2, idle_timeout: 20 });
let keyP: Promise<CryptoKey> | null = null;

const handle = makeApp({
  store: new PgStore(sql),
  fetch: (u, i) => fetch(u, i),
  authUser: async (jwt) => {
    const { data, error } = await admin.auth.getUser(jwt);
    return error || !data?.user ? null : { id: data.user.id, email: data.user.email ?? null, email_confirmed: Boolean(data.user.email_confirmed_at) };
  },
  deleteAuthUser: async (id) => {
    const { error } = await admin.auth.admin.deleteUser(id);
    if (error) throw new Error("delete user failed");
  },
  tokenKey: () => (keyP ||= importTokenKey(env("DDF_TOKEN_KEY"))),
  env,
  functionsBase: `${SUPABASE_URL}/functions/v1`,
  allowedOrigins: (env("DDF_STAGING_ORIGINS") || "https://datadrivenfootball.github.io").split(",").map((s) => s.trim()).filter(Boolean),
  now: () => new Date(),
  log: (f) => console.log(JSON.stringify(f)),
});

Deno.serve(handle);
