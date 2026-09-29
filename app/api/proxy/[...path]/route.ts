import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import {
  ACCESS_COOKIE,
  API_PREFIX,
  API_URL,
  clearSessionCookies,
  forwardedFor,
  isSameOrigin,
  REFRESH_COOKIE,
  refreshTokens,
  setSessionCookies,
  type TokenResponse,
} from "@/lib/server/session";

// Backend-for-frontend proxy: browser → /api/proxy/<path> → FastAPI /api/v1/<path>.
// Attaches the access token from the httpOnly cookie, refreshes it when expired,
// streams responses (incl. Server-Sent Events) and enforces same-origin mutations.

const FORWARD_REQUEST_HEADERS = ["content-type", "accept", "accept-language", "x-request-id"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "x-request-id", "x-ratelimit-remaining", "retry-after", "cache-control"];

async function handle(req: NextRequest, ctx: RouteContext<"/api/proxy/[...path]">): Promise<Response> {
  const { path } = await ctx.params;
  if (path.some((seg) => seg === ".." || seg === "." || seg.includes("\\"))) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }
  const method = req.method.toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && !isSameOrigin(req)) {
    return NextResponse.json({ detail: "Cross-site request blocked" }, { status: 403 });
  }
  const target = `${API_URL}${API_PREFIX}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const jar = await cookies();
  let access = jar.get(ACCESS_COOKIE)?.value;
  const refresh = jar.get(REFRESH_COOKIE)?.value;
  const xff = forwardedFor(req);
  let refreshed: TokenResponse | null = null;

  if (!access && refresh) {
    refreshed = await refreshTokens(refresh, xff);
    access = refreshed?.access_token;
  }

  const body = ["GET", "HEAD"].includes(method) ? undefined : await req.arrayBuffer();
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }
  if (xff) headers.set("x-forwarded-for", xff);

  const send = (token: string | undefined) => {
    const h = new Headers(headers);
    if (token) h.set("authorization", `Bearer ${token}`);
    return fetch(target, { method, headers: h, body, cache: "no-store", redirect: "manual" });
  };

  let upstream: Response;
  try {
    upstream = await send(access);
    if (upstream.status === 401 && refresh && !refreshed) {
      refreshed = await refreshTokens(refresh, xff);
      if (refreshed) upstream = await send(refreshed.access_token);
    }
  } catch {
    return NextResponse.json({ detail: "API is unreachable" }, { status: 502 });
  }

  const outHeaders = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const v = upstream.headers.get(name);
    if (v) outHeaders.set(name, v);
  }
  if (outHeaders.get("content-type")?.includes("text/event-stream")) {
    outHeaders.set("cache-control", "no-cache, no-transform");
    outHeaders.set("x-accel-buffering", "no");
  }
  const res = new NextResponse(upstream.body, { status: upstream.status, headers: outHeaders });
  if (refreshed) setSessionCookies(res, refreshed);
  else if (upstream.status === 401 && refresh) clearSessionCookies(res);
  return res;
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
