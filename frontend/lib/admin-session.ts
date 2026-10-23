// Server-only: imported by route handlers, never by client components.
import type { NextRequest } from 'next/server';

// Server-to-server: route handlers ask FastAPI directly whether the admin cookie is valid.
const FASTAPI_INTERNAL_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8011';
const ADMIN_COOKIE = 'session';

/**
 * True when the admin `session` cookie is accepted by FastAPI's `GET /api/auth/me` (200). Any
 * other answer, a missing cookie, or an unreachable backend is false: fail closed.
 */
export async function isAdminSession(req: NextRequest): Promise<boolean> {
  const session = req.cookies.get(ADMIN_COOKIE)?.value;
  if (!session) return false;
  try {
    const res = await fetch(`${FASTAPI_INTERNAL_URL}/api/auth/me`, {
      headers: { cookie: `${ADMIN_COOKIE}=${session}` },
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    });
    return res.status === 200;
  } catch (error) {
    console.error('Could not verify the admin session; refusing the room join.', error);
    return false;
  }
}
