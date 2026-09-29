import "server-only";

import type { NextResponse } from "next/server";

/** Internal URL of the FastAPI gateway (never exposed to browsers). */
export const API_URL = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const API_PREFIX = "/api/v1";

export const ACCESS_COOKIE = "cmg_at";
export const REFRESH_COOKIE = "cmg_rt";

const secure =
  process.env.COOKIE_SECURE === "true" ||
  (process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false");

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  access_expires_at: string;
  refresh_expires_at: string;
}

function maxAge(iso: string): number {
  return Math.max(1, Math.floor((new Date(iso).getTime() - Date.now()) / 1000));
}

export function setSessionCookies(res: NextResponse, tokens: TokenResponse): void {
  res.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: maxAge(tokens.access_expires_at) - 15, // refresh slightly before expiry
  });
  res.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: maxAge(tokens.refresh_expires_at),
  });
}

export function clearSessionCookies(res: NextResponse): void {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE]) {
    res.cookies.set(name, "", { httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: 0 });
  }
}

/** Forward the originating client address so the API can rate-limit per user IP. */
export function forwardedFor(req: Request): string | undefined {
  return req.headers.get("x-forwarded-for") ?? req.headers.get("x-real-ip") ?? undefined;
}

// Deduplicate concurrent refreshes within this Node process (the API also tolerates
// short-window reuse, which covers multiple web replicas).
const inflight = new Map<string, Promise<TokenResponse | null>>();

export function refreshTokens(refreshToken: string, xff?: string): Promise<TokenResponse | null> {
  const existing = inflight.get(refreshToken);
  if (existing) return existing;
  const p = (async () => {
    try {
      const res = await fetch(`${API_URL}${API_PREFIX}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(xff ? { "X-Forwarded-For": xff } : {}) },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      });
      return res.ok ? ((await res.json()) as TokenResponse) : null;
    } catch {
      return null;
    } finally {
      setTimeout(() => inflight.delete(refreshToken), 5_000);
    }
  })();
  inflight.set(refreshToken, p);
  return p;
}

/** CSRF defence for cookie-authenticated mutations: require a same-origin request. */
export function isSameOrigin(req: Request): boolean {
  const site = req.headers.get("sec-fetch-site");
  if (site) return site === "same-origin" || site === "none";
  const origin = req.headers.get("origin");
  if (!origin) return true; // non-browser clients (no ambient cookies involved)
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/**
 * Server-side call to the API as the signed-in user (cookie session), refreshing the
 * access token if needed. Returns the response plus any rotated tokens to persist.
 */
export async function backendFetch(
  path: string,
  access: string | undefined,
  refresh: string | undefined,
  xff?: string,
): Promise<{ res: Response; refreshed: TokenResponse | null }> {
  let refreshed: TokenResponse | null = null;
  let token = access;
  if (!token && refresh) {
    refreshed = await refreshTokens(refresh, xff);
    token = refreshed?.access_token;
  }
  const call = (t?: string) =>
    fetch(`${API_URL}${API_PREFIX}${path}`, {
      headers: { ...(t ? { authorization: `Bearer ${t}` } : {}), ...(xff ? { "x-forwarded-for": xff } : {}) },
      cache: "no-store",
    });
  let res = await call(token);
  if (res.status === 401 && refresh && !refreshed) {
    refreshed = await refreshTokens(refresh, xff);
    if (refreshed) res = await call(refreshed.access_token);
  }
  return { res, refreshed };
}
