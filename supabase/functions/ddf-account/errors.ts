// Errors the router turns into JSON. `message` is shown to the user, so it never
// carries a token, a cookie or a raw platform body.
export class AppError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export type Fetch = (input: string | URL, init?: RequestInit) => Promise<Response>;

export async function getJSON(f: Fetch, url: string, init: RequestInit = {}, platform = "platform"): Promise<{ status: number; body: unknown }> {
  let r: Response;
  try {
    r = await f(url, { ...init, signal: AbortSignal.timeout(15000) });
  } catch {
    throw new AppError(502, `${platform}_unreachable`, `We could not reach ${platform} just now. Try again in a minute.`);
  }
  if (r.status === 401 || r.status === 403 || r.status === 404) {
    await r.body?.cancel();
    return { status: r.status, body: null };
  }
  if (!r.ok) {
    await r.body?.cancel();
    throw new AppError(502, `${platform}_error`, `${platform} answered with an error (${r.status}). Try again in a minute.`);
  }
  return { status: r.status, body: await r.json() };
}
