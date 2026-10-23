'use client';

import { useCallback } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

/**
 * Reads and writes several query-string params at once, so filters survive a reload and can be
 * linked to. `set` merges: a `null`/empty value removes the param. Needs a Suspense boundary.
 */
export function useUrlParams(): [
  URLSearchParams,
  (changes: Record<string, string | null>) => void,
] {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const set = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(changes)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router]
  );
  return [params, set];
}
