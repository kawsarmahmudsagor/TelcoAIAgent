'use client';

import { useState } from 'react';
import { BellRingIcon, Loader2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { PortalButton } from '@/components/portal/ui/link-button';
import { adminApi } from '@/lib/admin-api';
import { invalidateAdmin } from '@/lib/admin-query';
import { ApiError } from '@/lib/api-client';

/** Runs the nudge sweep now, instead of waiting for the 15-minute schedule. */
export function RunNudgesButton() {
  const [running, setRunning] = useState(false);

  async function run() {
    if (running) return;
    setRunning(true);
    try {
      const { created } = await adminApi.runNudges();
      const total = Object.values(created).reduce((sum, n) => sum + (n ?? 0), 0);
      toast.success(
        total > 0
          ? `Created ${total} ${total === 1 ? 'notification' : 'notifications'}`
          : 'No new notifications'
      );
      invalidateAdmin(['subscriber']);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : 'Could not run the nudges. Try again.'
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <PortalButton variant="glass" onClick={() => void run()} disabled={running} aria-busy={running}>
      {running ? (
        <Loader2Icon className="animate-spin" aria-hidden="true" />
      ) : (
        <BellRingIcon aria-hidden="true" />
      )}
      Run nudges now
    </PortalButton>
  );
}
