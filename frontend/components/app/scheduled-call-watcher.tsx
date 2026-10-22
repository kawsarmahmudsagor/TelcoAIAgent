'use client';

import { useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { api } from '@/lib/api-client';

const POLL_INTERVAL_MS = 5000;
// in_progress (not dispatched) because the scheduler only sets it once the
// LiveKit room actually exists -- so we never ring for a room that isn't there yet.
const LIVE_STATUSES = new Set(['in_progress']);
const INCOMING_PATH_PREFIX = '/dashboard/incoming/';

/**
 * Polls the cold-call schedule and, the moment a call goes live
 * (pending -> in_progress), navigates the admin browser to the incoming-call
 * screen for it, where it rings until answered (joins the conversation UI),
 * declined, or missed -- so testing a scheduled call feels like actually
 * receiving one.
 *
 * Only reacts to a transition observed between two polls (not just "is
 * live"), so pre-existing/stale entries that were already dispatched before
 * this component mounted don't trigger an immediate redirect.
 */
export function ScheduledCallWatcher() {
  const router = useRouter();
  const pathname = usePathname();
  // Read through a ref so the poll loop isn't torn down (and its transition
  // history lost) on every navigation.
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;
  const previousStatusRef = useRef<Map<string, string> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      let entries;
      try {
        entries = await api.schedule();
      } catch {
        return; // transient error, next poll will retry
      }
      if (cancelled) return;

      const previousStatus = previousStatusRef.current;
      const nextStatus = new Map(entries.map((entry) => [entry.id, entry.status]));

      // Already ringing for a call -- don't yank the user to another one.
      const alreadyRinging = pathnameRef.current.startsWith(INCOMING_PATH_PREFIX);

      if (previousStatus !== null && !alreadyRinging) {
        for (const entry of entries) {
          // Phone calls ring a real phone, not this browser.
          if (entry.dial_number) continue;
          const wasLive = LIVE_STATUSES.has(previousStatus.get(entry.id) ?? '');
          const isLive = LIVE_STATUSES.has(entry.status);
          // Already picked up (e.g. in another tab) -- nothing left to ring for.
          if (!wasLive && isLive && !entry.answered_at) {
            router.push(`${INCOMING_PATH_PREFIX}${entry.id}`);
            break;
          }
        }
      }

      previousStatusRef.current = nextStatus;
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [router]);

  return null;
}
