import { NextResponse, type NextRequest } from "next/server";
import { API_PREFIX, API_URL } from "@/lib/server/session";

export async function GET(req: NextRequest) {
  const returnTo = req.nextUrl.searchParams.get("return_to") ?? "/dashboard";
  const res = await fetch(
    `${API_URL}${API_PREFIX}/auth/sso/authorize?return_to=${encodeURIComponent(returnTo)}`,
    { cache: "no-store" },
  ).catch(() => null);
  if (!res || !res.ok) {
    return NextResponse.redirect(new URL("/login?error=sso_unavailable", req.url));
  }
  const { url } = (await res.json()) as { url: string };
  return NextResponse.redirect(url);
}
