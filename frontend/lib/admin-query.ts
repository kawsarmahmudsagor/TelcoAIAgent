'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError } from '@/lib/api-client';

/** The admin portal's data sets. Anything that changes one (a form, a status change) invalidates its key. */
export type AdminKey =
  | 'overview'
  | 'subscribers'
  | 'subscriber'
  | 'transactions'
  | 'txnStats'
  | 'cases'
  | 'caseStats'
  | 'network'
  | 'monitor'
  | 'offers'
  | 'packages'
  | 'kbStatus';

const INVALIDATE = 'admin:invalidate';

// One bus for the whole tab: every mounted query listens, and each refetches when its key is named.
const bus = new EventTarget();

/** Refetches the queries for `keys`, or every admin query when called without arguments. */
export function invalidateAdmin(keys?: AdminKey[]): void {
  bus.dispatchEvent(new CustomEvent<AdminKey[] | null>(INVALIDATE, { detail: keys ?? null }));
}

export interface AdminQuery<T> {
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
  return new ApiError(0, 'The server could not be reached. Check your connection and try again.');
}

/**
 * Loads one admin data set and keeps it fresh: it refetches on `reload()`, on `invalidateAdmin()`
 * naming `key` (or no key), and when `deps` changes (compared by value; pass the inputs the
 * fetcher closes over, e.g. a filter or page). The previous `data` stays in place while a refetch
 * runs, so tables and tiles don't flash. A 401 means the admin session is gone: the browser goes
 * to `/login`.
 */
export function useAdminQuery<T>(
  key: AdminKey,
  fetcher: () => Promise<T>,
  deps?: unknown[]
): AdminQuery<T> {
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
      const keys = (event as CustomEvent<AdminKey[] | null>).detail;
      if (keys === null || keys.includes(key)) reload();
    }
    bus.addEventListener(INVALIDATE, onInvalidate);
    return () => bus.removeEventListener(INVALIDATE, onInvalidate);
  }, [key, reload]);

  const depsKey = JSON.stringify(deps ?? null);

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
          router.replace('/login');
          return;
        }
        setState((prev) => ({ data: prev.data, error: apiError, loading: false }));
      }
    );
    return () => {
      cancelled = true;
    };
  }, [key, depsKey, version, router]);

  return { ...state, reload };
}
