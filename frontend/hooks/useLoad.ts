'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export interface LoadState<T> {
  /** The last successful result; kept while a reload is in flight, so nothing flashes. */
  data: T | undefined;
  /** Message of the last failure, cleared by the next success. */
  error: string | null;
  /** True only until the first result (or failure) arrives. */
  loading: boolean;
  /** Fetches again in the background (no skeleton), e.g. after a mutation. */
  reload: () => Promise<void>;
  /** Shows the loading state and fetches again: the "Try again" button. */
  retry: () => Promise<void>;
  /** Replaces the data locally, e.g. with a server response to a mutation. */
  setData: (data: T) => void;
}

/**
 * Runs `load` on mount (and whenever `deps` change) and exposes loading / error / reload, so
 * each panel can fail and retry on its own. Responses that arrive after a newer request started
 * are dropped. `pollMs` refetches on an interval while it is a number (pass null to stop).
 */
export function useLoad<T>(
  load: () => Promise<T>,
  deps: React.DependencyList = [],
  {
    pollMs = null,
    fallbackError = 'Could not load this.',
  }: { pollMs?: number | null; fallbackError?: string } = {}
): LoadState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const token = useRef(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    const mine = ++token.current;
    try {
      const result = await loadRef.current();
      if (mine !== token.current) return;
      setData(result);
      setError(null);
    } catch (err) {
      if (mine !== token.current) return;
      setError(err instanceof Error && err.message ? err.message : fallbackError);
    } finally {
      if (mine === token.current) setLoading(false);
    }
  }, [fallbackError]);

  const retry = useCallback(async () => {
    setLoading(true);
    setError(null);
    await reload();
  }, [reload]);

  useEffect(() => {
    setLoading(true);
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (pollMs === null) return;
    const id = setInterval(() => void reload(), pollMs);
    return () => clearInterval(id);
  }, [pollMs, reload]);

  return { data, error, loading, reload, retry, setData };
}
