// Server-only: imported by route handlers, never by client components.
import type { NextRequest } from 'next/server';

// Server-to-server: route handlers ask FastAPI directly who the portal cookie belongs to.
const FASTAPI_INTERNAL_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8011';
const PORTAL_COOKIE = 'portal_session';

/**
 * The signed-in customer's subscriber id, verified by FastAPI's `GET /api/me` against the
 * `portal_session` cookie; null (a guest) without the cookie or on any non-200 answer.
 */
export async function resolveSubscriberId(req: NextRequest): Promise<string | null> {
  const session = req.cookies.get(PORTAL_COOKIE)?.value;
  if (!session) return null;
  try {
    const res = await fetch(`${FASTAPI_INTERNAL_URL}/api/me`, {
      headers: { cookie: `${PORTAL_COOKIE}=${session}` },
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    });
    if (res.status !== 200) return null;
    const me = (await res.json()) as { subscriber_id?: unknown };
    return typeof me.subscriber_id === 'string' ? me.subscriber_id : null;
  } catch (error) {
    console.error('Could not resolve the portal session; treating the caller as a guest.', error);
    return null;
  }
}
