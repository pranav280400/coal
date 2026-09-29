import { NextResponse } from "next/server";
import {
  API_PREFIX,
  API_URL,
  forwardedFor,
  isSameOrigin,
  setSessionCookies,
  type TokenResponse,
} from "@/lib/server/session";

export async function POST(req: Request) {
  if (!isSameOrigin(req)) return NextResponse.json({ detail: "Cross-site request blocked" }, { status: 403 });
  let body: { username?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  }
  const xff = forwardedFor(req);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${API_PREFIX}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(xff ? { "X-Forwarded-For": xff } : {}) },
      body: JSON.stringify({ username: body.username ?? "", password: body.password ?? "" }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "Authentication service is unavailable" }, { status: 503 });
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return NextResponse.json(data, { status: res.status });
  const out = NextResponse.json({ ok: true });
  setSessionCookies(out, data as TokenResponse);
  return out;
}
