import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { ACCESS_COOKIE, backendFetch, forwardedFor, REFRESH_COOKIE, setSessionCookies } from "@/lib/server/session";

// Opens a stored file (evidence photo, document, report) in a new tab: resolves a short-lived
// pre-signed object-storage URL as the signed-in user and redirects to it. Authorisation is
// enforced by the API for every request, so links are safe to share only with permitted users.

const PATHS: Record<string, (id: string, req: NextRequest) => string> = {
  media: (id) => `/media-files/${id}/url`,
  document: (id) => `/documents/${id}/download`,
  report: (id, req) => `/reports/${id}/download?format=${req.nextUrl.searchParams.get("format") === "xlsx" ? "xlsx" : "pdf"}`,
};

export async function GET(req: NextRequest, ctx: RouteContext<"/api/files/[kind]/[id]">) {
  const { kind, id } = await ctx.params;
  const build = PATHS[kind];
  if (!build || !/^[0-9a-f-]{36}$/i.test(id)) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  const jar = await cookies();
  const { res, refreshed } = await backendFetch(build(id, req), jar.get(ACCESS_COOKIE)?.value, jar.get(REFRESH_COOKIE)?.value, forwardedFor(req));
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    return new NextResponse(data.detail ?? "File not available", { status: res.status, headers: { "content-type": "text/plain; charset=utf-8" } });
  }
  const { url } = (await res.json()) as { url: string };
  const out = NextResponse.redirect(url, 302);
  out.headers.set("Cache-Control", "no-store");
  if (refreshed) setSessionCookies(out, refreshed);
  return out;
}
