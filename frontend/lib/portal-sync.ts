'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError } from '@/lib/api-client';

/** The portal's data sets. Anything that changes one (a form, an agent event) invalidates its key. */
export type PortalKey =
  | 'me'
  | 'summary'
  | 'usage'
  | 'transactions'
  | 'packages'
  | 'recommendations'
  | 'offers'
  | 'cases'
  | 'network';

const INVALIDATE = 'portal:invalidate';

// One bus for the whole tab: every mounted query listens, and each refetches when its key is named.
const bus = new EventTarget();

/** Refetches the queries for `keys`, or every portal query when called without arguments. */
export function invalidatePortal(keys?: PortalKey[]): void {
  bus.dispatchEvent(new CustomEvent<PortalKey[] | null>(INVALIDATE, { detail: keys ?? null }));
}

export interface PortalQuery<T> {
  data?: T;
  error?: ApiError;
  loading: boolean;
  reload(): void;
}

interface QueryState<T> {
  data?: T;
  error?: ApiError;
  loading: boolean;
}

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  // fetch() rejects with a TypeError when the server can't be reached at all.
  return new ApiError(0, 'The portal could not be reached. Check your connection and try again.');
}

/**
 * Loads one portal data set and keeps it fresh: it refetches on `reload()`, on
 * `invalidatePortal()` naming `key` (or no key), and when `args` changes (compared by value; pass
 * the inputs the fetcher closes over, e.g. a period). The previous `data` stays in place while a
 * refetch runs, so cards don't flash. A 401 means the portal session is gone: the browser goes
 * back to the persona picker at `/`.
 */
export function usePortalQuery<T>(
  key: PortalKey,
  fetcher: () => Promise<T>,
  args?: unknown
): PortalQuery<T> {
  const router = useRouter();
  const [state, setState] = useState<QueryState<T>>({ loading: true });
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  // The latest fetcher, without making callers memoise it.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    function onInvalidate(event: Event) {
      const keys = (event as CustomEvent<PortalKey[] | null>).detail;
      if (keys === null || keys.includes(key)) reload();
    }
    bus.addEventListener(INVALIDATE, onInvalidate);
    return () => bus.removeEventListener(INVALIDATE, onInvalidate);
  }, [key, reload]);

  const argsKey = JSON.stringify(args ?? null);

  useEffect(() => {
    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true }));
    fetcherRef.current().then(
      (data) => {
        if (!cancelled) setState({ data, loading: false });
      },
      (error: unknown) => {
        if (cancelled) return;
        const apiError = asApiError(error);
        if (apiError.status === 401) {
          router.replace('/');
          return;
        }
        setState((prev) => ({ data: prev.data, error: apiError, loading: false }));
      }
    );
    return () => {
      cancelled = true;
    };
  }, [key, argsKey, version, router]);

  return { ...state, reload };
}
