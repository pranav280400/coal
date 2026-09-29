import { NextResponse, type NextRequest } from "next/server";
import { API_PREFIX, API_URL, setSessionCookies, type TokenResponse } from "@/lib/server/session";

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get("code");
  const state = req.nextUrl.searchParams.get("state");
  const providerError = req.nextUrl.searchParams.get("error");
  if (providerError || !code || !state) {
    return NextResponse.redirect(new URL("/login?error=sso_denied", req.url));
  }
  const res = await fetch(`${API_URL}${API_PREFIX}/auth/sso/callback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, state }),
    cache: "no-store",
  }).catch(() => null);
  if (!res || !res.ok) {
    const detail = res ? (((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "") : "";
    const url = new URL("/login", req.url);
    url.searchParams.set("error", "sso_failed");
    if (detail) url.searchParams.set("detail", detail.slice(0, 200));
    return NextResponse.redirect(url);
  }
  const data = (await res.json()) as TokenResponse & { return_to: string };
  const target = data.return_to?.startsWith("/") && !data.return_to.startsWith("//") ? data.return_to : "/dashboard";
  const out = NextResponse.redirect(new URL(target, req.url));
  setSessionCookies(out, data);
  return out;
}
