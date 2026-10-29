const TOKEN_KEY = "secbrain_token";

/**
 * Resolve the API base URL **at runtime** (in the browser), so the app works
 * when opened from another device without rebuilding.
 *
 * Resolution order:
 *  1. NEXT_PUBLIC_API_URL="same-origin"  -> "" (relative): the UI and API are
 *     served from one origin (e.g. behind a reverse proxy / tunnel). No CORS.
 *  2. NEXT_PUBLIC_API_URL set to a real absolute URL (not localhost) -> use it.
 *  3. Otherwise (unset, or the localhost default): derive from the browser's
 *     current host, using NEXT_PUBLIC_API_PORT (default 8000). So opening
 *     http://<server-ip-or-host>:3000 makes the API target
 *     http://<server-ip-or-host>:8000 automatically.
 */
export function apiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_URL || "").trim();

  if (configured === "same-origin") return "";

  const isLocalhost = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/?$/i.test(configured);
  if (configured && !isLocalhost) return configured.replace(/\/$/, "");

  // Derive from the current browser host (handles LAN IPs, hostnames, tunnels
  // where both ports are reachable).
  if (typeof window !== "undefined") {
    const port = (process.env.NEXT_PUBLIC_API_PORT || "8000").trim();
    const host = window.location.hostname;
    return port ? `${window.location.protocol}//${host}:${port}` : `${window.location.protocol}//${host}`;
  }

  // Server-side fallback (SSR/prerender): only used if ever called off-browser.
  return configured || "http://localhost:8000";
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  isForm?: boolean;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, isForm = false } = opts;
  const headers: Record<string, string> = {};
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    if (isForm) {
      payload = body as FormData;
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }
  const base = apiBase();
  let res: Response;
  try {
    res = await fetch(`${base}/api/v1${path}`, { method, headers, body: payload });
  } catch (error) {
    const reason = error instanceof Error ? error.message : "Network request failed";
    throw new ApiError(
      0,
      `Cannot reach SecBrain API at ${base || "this site's origin"}. Check that the backend is reachable from your device (and NEXT_PUBLIC_API_URL / CORS if set). (${reason})`
    );
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : null) || `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

