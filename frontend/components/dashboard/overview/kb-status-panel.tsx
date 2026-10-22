'use client';

import Link from 'next/link';
import { AlertTriangleIcon } from 'lucide-react';
import { SectionCard } from '@/components/dashboard/section-card';
import { StatusPill } from '@/components/dashboard/status-pill';
import { TableState } from '@/components/dashboard/table-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useLoad } from '@/hooks/useLoad';
import { type RagStatus, api } from '@/lib/api-client';

const POLL_MS = 10_000;

/** Whether the agent can actually answer from the knowledge base, and what is in it. */
export function KbStatusPanel({ className }: { className?: string }) {
  const { data, error, loading, retry } = useLoad(() => api.dashboard.ragStatus(), [], {
    fallbackError: 'Could not load the knowledge base status.',
    pollMs: POLL_MS,
  });

  return (
    <SectionCard
      className={className}
      title="Knowledge base"
      action={
        <Link
          href="/dashboard/knowledge"
          aria-label="Manage the knowledge base"
          className="text-primary focus-visible:ring-ring/50 rounded-sm text-sm font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-[3px]"
        >
          Manage
        </Link>
      }
    >
      {error && !data ? (
        <TableState error={error} onRetry={() => void retry()} />
      ) : loading || !data ? (
        <div className="space-y-3" aria-busy="true">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : (
        <KbStatusBody status={data} />
      )}
    </SectionCard>
  );
}

function KbStatusBody({ status }: { status: RagStatus }) {
  const s = status.sources;
  const searchable = s.ready + s.stale;
  const inFlight = s.pending + s.processing;
  const headline = !status.rag_enabled
    ? { tone: 'muted' as const, label: 'Off for the agent' }
    : !status.embedding_ready || !status.chroma_reachable
      ? { tone: 'danger' as const, label: 'Not working' }
      : inFlight > 0
        ? { tone: 'info' as const, label: 'Updating', pulse: true }
        : { tone: 'success' as const, label: 'Agent can search it' };

  // Proportional bar of source states; widths only, the counts are listed underneath.
  const segments = [
    { key: 'ready', count: searchable, className: 'bg-success' },
    { key: 'busy', count: inFlight, className: 'bg-info' },
    { key: 'failed', count: s.failed, className: 'bg-destructive' },
    { key: 'disabled', count: s.disabled, className: 'bg-muted-foreground/40' },
  ];

  return (
    <div className="space-y-4">
      <StatusPill tone={headline.tone} pulse={headline.pulse}>
        {headline.label}
      </StatusPill>

      {!status.embedding_ready && (
        <Problem>
          No OpenRouter key for embeddings, so nothing can be added or searched. Add one on the{' '}
          <Link href="/dashboard/chatbot?tab=model" className="underline underline-offset-2">
            Chatbot page
          </Link>
          .
        </Problem>
      )}
      {status.embedding_ready && !status.chroma_reachable && (
        <Problem>The vector store (Chroma) isn&apos;t reachable. Check that it is running.</Problem>
      )}

      {s.total === 0 ? (
        <p className="text-muted-foreground text-sm">
          Nothing added yet. Upload your FAQ or price list so the agent can answer from it.
        </p>
      ) : (
        <>
          <div className="bg-muted flex h-2 overflow-hidden rounded-full" aria-hidden="true">
            {segments.map(
              (seg) =>
                seg.count > 0 && (
                  <span
                    key={seg.key}
                    className={seg.className}
                    style={{ width: `${(seg.count / s.total) * 100}%` }}
                  />
                )
            )}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <Stat label="Searchable sources" value={`${searchable} of ${s.total}`} />
            <Stat label="Chunks" value={status.total_chunks.toLocaleString()} />
            <Stat label="Processing" value={inFlight} />
            <Stat
              label="Failed"
              value={s.failed}
              className={s.failed > 0 ? 'text-destructive' : undefined}
            />
          </dl>
        </>
      )}

      {status.embedding_migration_status === 'running' && (
        <p className="text-info text-sm">Re-embedding with {status.embedding_migration_target}…</p>
      )}
      <p className="text-muted-foreground font-mono text-xs break-all">{status.embedding_model}</p>
    </div>
  );
}

function Stat({
  label,
  value,
  className,
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
}) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className={`font-medium tabular-nums ${className ?? ''}`}>{value}</dd>
    </div>
  );
}

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p className="bg-destructive/8 text-destructive flex gap-2 rounded-md p-3 text-sm" role="alert">
      <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}
