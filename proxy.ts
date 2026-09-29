import { NextResponse, type NextRequest } from "next/server";

// Gate application pages on the presence of a session cookie. The real authorisation
// happens in the API on every request; this only avoids rendering the shell for
// signed-out visitors and sends them to the login page with a return path.

// "/" is the public marketing landing; the application lives under /dashboard.
const PUBLIC_PATHS = ["/", "/login", "/register", "/forgot-password", "/reset-password", "/offline"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = request.cookies.has("cmg_rt") || request.cookies.has("cmg_at");
  const isPublic = PUBLIC_PATHS.some((p) => (p === "/" ? pathname === "/" : pathname === p || pathname.startsWith(`${p}/`)));

  if (!hasSession && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  // Signed-in users visiting /login are not bounced away: a stale cookie would otherwise
  // cause a redirect loop. The proxy clears cookies whenever a refresh fails.
  return NextResponse.next();
}

export const config = {
  matcher: [
    // Pages only: skip API routes, Next internals, the service worker and static assets.
    "/((?!api|_next/static|_next/image|sw.js|manifest.webmanifest|icons|images|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|webp|ico|txt)$).*)",
  ],
};
