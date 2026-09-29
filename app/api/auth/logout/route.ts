import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { API_PREFIX, API_URL, clearSessionCookies, isSameOrigin, REFRESH_COOKIE } from "@/lib/server/session";

export async function POST(req: Request) {
  if (!isSameOrigin(req)) return NextResponse.json({ detail: "Cross-site request blocked" }, { status: 403 });
  const jar = await cookies();
  const refresh = jar.get(REFRESH_COOKIE)?.value;
  if (refresh) {
    // Revoke server-side; failure to reach the API must not block local sign-out.
    await fetch(`${API_URL}${API_PREFIX}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    }).catch(() => undefined);
  }
  const res = NextResponse.json({ ok: true });
  clearSessionCookies(res);
  return res;
}
