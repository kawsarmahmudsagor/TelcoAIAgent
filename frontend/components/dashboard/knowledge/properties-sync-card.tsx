'use client';

import { useState } from 'react';
import { Loader2Icon, RefreshCwIcon } from 'lucide-react';
import { toast } from 'sonner';
import { SectionCard } from '@/components/dashboard/section-card';
import { StatusPill } from '@/components/dashboard/status-pill';
import { RAG_SOURCE_STATUS, styleOf } from '@/components/dashboard/status-tones';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { type RagSource, api } from '@/lib/api-client';
import { formatRelative } from '@/lib/format';

/** The property listings as a knowledge source: one passage per active listing, so the agent
 * can answer descriptive questions ("which flats have a gym?"). Kept in sync automatically once
 * it exists; the button forces a sync now. */
export function PropertiesSyncCard({
  source,
  loading,
  disabled,
  onSynced,
}: {
  source: RagSource | null;
  loading: boolean;
  disabled?: boolean;
  onSynced: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const status = source ? styleOf(RAG_SOURCE_STATUS, source.status) : null;
  const running = source?.status === 'pending' || source?.status === 'processing';

  async function sync() {
    setBusy(true);
    try {
      await api.rag.syncProperties();
      toast.success(source ? 'Syncing listings' : 'Listings added to the knowledge base', {
        description: 'Runs in the background.',
      });
      onSynced();
    } catch (err) {
      toast.error('Could not sync listings', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <SectionCard
      className="lg:self-start"
      title="Property listings"
      description="Lets the agent answer questions about your listings' descriptions and amenities."
    >
      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-9 w-32" />
        </div>
      ) : (
        <div className="grid gap-4">
          {source && status ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div className="col-span-2">
                <dt className="sr-only">Status</dt>
                <dd>
                  <StatusPill
                    tone={status.tone}
                    pulse={status.pulse}
                    title={source.error ?? undefined}
                  >
                    {status.label}
                  </StatusPill>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Passages</dt>
                <dd className="font-medium tabular-nums">{source.chunk_count}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Last synced</dt>
                <dd className="font-medium">
                  {source.last_indexed_at ? formatRelative(source.last_indexed_at) : 'Not yet'}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-muted-foreground text-sm">
              Not added yet. Once added, it updates by itself whenever a listing changes.
            </p>
          )}
          <Button
            variant={source ? 'outline' : 'default'}
            size="sm"
            className="justify-self-start"
            onClick={() => void sync()}
            disabled={busy || running || disabled}
          >
            {busy ? (
              <Loader2Icon className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCwIcon aria-hidden="true" />
            )}
            {source ? 'Sync now' : 'Add listings'}
          </Button>
        </div>
      )}
    </SectionCard>
  );
}
