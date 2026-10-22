import { type NextRequest, NextResponse } from 'next/server';

// When the browser talks to FastAPI directly (another origin), the `session` cookie belongs to
// that origin and never reaches this server, so there is nothing to check here: the dashboard
// layout's api.me() call is the gate. Inlined at build time.
const API_ON_OTHER_ORIGIN = Boolean(process.env.NEXT_PUBLIC_FASTAPI_URL);

/**
 * Sends signed-out visitors to /login before the dashboard shell renders. It only checks that a
 * session cookie exists (the JWT is verified by FastAPI on every API call), so it is a fast-path
 * redirect, not the security boundary.
 */
export function middleware(request: NextRequest) {
  if (API_ON_OTHER_ORIGIN || request.cookies.has('session')) {
    return NextResponse.next();
  }
  const login = new URL('/login', request.url);
  login.searchParams.set('next', request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ['/dashboard/:path*'],
};
