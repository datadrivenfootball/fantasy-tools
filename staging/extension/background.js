/* DDF: Connect ESPN (JEG-1732). Manifest V3 service worker.
 * The DDF page (and only it: externally_connectable plus the origin check below) asks this extension to
 * connect ESPN. The extension reads ESPN's own session cookies (espn_s2, SWID) for espn.com and sends
 * them straight to DDF's ddf-account function with the user's DDF sign-in. The cookies never go back
 * to the page, are never stored here, and are never logged. DDF never sees the ESPN password. */
const FN = "https://iskiybsimubiujwuchsl.supabase.co/functions/v1/ddf-account";
const PAGES = ["https://datadrivenfootball.github.io", "http://localhost:8791"];

async function espnSession() {
  const get = (name) => chrome.cookies.get({ url: "https://www.espn.com/", name });
  const [s2, swid] = await Promise.all([get("espn_s2"), get("SWID")]);
  return s2 && s2.value && swid && swid.value ? { espn_s2: s2.value, swid: swid.value } : null;
}

async function connectEspn(jwt) {
  if (typeof jwt !== "string" || jwt.length < 20) return { ok: false, code: "signed_out", message: "Sign in to DDF first." };
  const session = await espnSession();
  if (!session) return { ok: false, code: "espn_signed_out", message: "You're not signed in to ESPN in this browser. Sign in at espn.com, then press Connect ESPN again." };
  let r;
  try {
    r = await fetch(FN + "/espn/session", { method: "POST", headers: { authorization: "Bearer " + jwt, "content-type": "application/json" }, body: JSON.stringify(session) });
  } catch (_e) {
    return { ok: false, code: "network", message: "Couldn't reach DDF. Check your connection and try again." };
  }
  const j = await r.json().catch(() => ({}));
  return r.ok ? { ok: true, connection: j.connection, season: j.season, leagues: j.leagues }
    : { ok: false, code: (j.error && j.error.code) || "error", message: (j.error && j.error.message) || "DDF answered " + r.status };
}

chrome.runtime.onMessageExternal.addListener((msg, sender, reply) => {
  if (!PAGES.includes(sender.origin)) { reply({ ok: false, code: "bad_origin" }); return; }
  if (msg && msg.type === "ping") { reply({ ok: true, version: chrome.runtime.getManifest().version }); return; }
  if (msg && msg.type === "connect-espn") { connectEspn(msg.jwt).then(reply); return true; }
  reply({ ok: false, code: "unknown_message" });
});
