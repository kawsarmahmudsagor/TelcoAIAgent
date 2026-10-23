import { type NextRequest, NextResponse } from 'next/server';

// When the browser talks to FastAPI directly (another origin), the `session` cookie belongs to
// that origin and never reaches this server, so there is nothing to check here: the dashboard
// layout's api.me() call is the gate. Inlined at build time.
const API_ON_OTHER_ORIGIN = Boolean(process.env.NEXT_PUBLIC_FASTAPI_URL);

/**
 * Fast-path redirects for signed-out visitors, before any shell renders:
 * - /dashboard/* without the admin `session` cookie goes to /login (with `next`);
 * - /portal/* without the customer `portal_session` cookie goes to /signin (with `next`).
 * Only the cookie's presence is checked (FastAPI verifies the JWT on every API call), so this is
 * not the security boundary.
 */
export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith('/portal')) {
    if (API_ON_OTHER_ORIGIN || request.cookies.has('portal_session')) {
      return NextResponse.next();
    }
    const signIn = new URL('/signin', request.url);
    signIn.searchParams.set('next', request.nextUrl.pathname + request.nextUrl.search);
    return NextResponse.redirect(signIn);
  }

  if (API_ON_OTHER_ORIGIN || request.cookies.has('session')) {
    return NextResponse.next();
  }
  const login = new URL('/login', request.url);
  login.searchParams.set('next', request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ['/dashboard/:path*', '/portal/:path*'],
};
