/**
 * Where a customer goes after signing in: a `?next=` path inside the portal, otherwise the
 * overview. Anything else (another origin, `//host`, `/\host`, the admin dashboard) is ignored,
 * so `next` can't be used as an open redirect.
 */
export function portalNextPath(next: string | null | undefined): string {
  if (!next || !/^\/portal(?:[/?#]|$)/.test(next) || next.includes('\\')) return '/portal';
  return next;
}

/** The sign-in page for a portal path, keeping where the customer was going. */
export function signInHref(next: string): string {
  return `/signin?next=${encodeURIComponent(next)}`;
}
