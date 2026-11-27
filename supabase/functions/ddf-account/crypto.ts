// AES-256-GCM sealing for platform tokens (JEG-1732). The key is the DDF_TOKEN_KEY
// function secret (32 random bytes, base64); it never reaches the database or a log.
// The additional data binds a ciphertext to its user and platform, so a row copied
// onto another user cannot be opened.

const enc = new TextEncoder();
const dec = new TextDecoder();

export async function importTokenKey(b64: string | undefined): Promise<CryptoKey> {
  if (!b64) throw new Error("DDF_TOKEN_KEY is not set");
  const raw = Uint8Array.from(atob(b64.trim()), (c) => c.charCodeAt(0));
  if (raw.length !== 32) throw new Error("DDF_TOKEN_KEY must be 32 bytes, base64");
  return await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export type Sealed = { ciphertext: Uint8Array; iv: Uint8Array };

export async function seal(key: CryptoKey, value: unknown, aad: string): Promise<Sealed> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: enc.encode(aad) },
    key,
    enc.encode(JSON.stringify(value)),
  );
  return { ciphertext: new Uint8Array(ct), iv };
}

export async function unseal<T>(key: CryptoKey, sealed: Sealed, aad: string): Promise<T> {
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: new Uint8Array(sealed.iv), additionalData: enc.encode(aad) },
    key,
    new Uint8Array(sealed.ciphertext),
  );
  return JSON.parse(dec.decode(pt)) as T;
}

export function randomToken(bytes = 32): string {
  const b = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
