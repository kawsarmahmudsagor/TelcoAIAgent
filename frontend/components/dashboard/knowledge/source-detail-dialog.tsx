'use client';

import { useState } from 'react';
import { ExternalLinkIcon, Loader2Icon, RefreshCwIcon, RotateCcwIcon } from 'lucide-react';
import { toast } from 'sonner';
import { StatusPill } from '@/components/dashboard/status-pill';
import {
  JOB_STATUS,
  JOB_TYPE,
  RAG_PAGE_STATUS,
  RAG_SOURCE_STATUS,
  RAG_SOURCE_TYPE,
  styleOf,
} from '@/components/dashboard/status-tones';
import { TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useLoad } from '@/hooks/useLoad';
import { type EmbeddingJob, type RagSource, api } from '@/lib/api-client';
import { formatBytes, formatDateTime, formatRelative } from '@/lib/format';
import { sourceOrigin } from './source-table';

const POLL_MS = 3000;

export function SourceDetailDialog({
  source,
  onOpenChange,
  onChanged,
}: {
  /** The row it was opened from; null = closed. */
  source: RagSource | null;
  onOpenChange: (open: boolean) => void;
  onChanged: () => void;
}) {
  return (
    <Dialog open={source !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-2xl">
        {source && <DetailBody key={source.id} row={source} onChanged={onChanged} />}
      </DialogContent>
    </Dialog>
  );
}

function DetailBody({ row, onChanged }: { row: RagSource; onChanged: () => void }) {
  const [pollMs, setPollMs] = useState<number | null>(null);
  const [acting, setActing] = useState(false);
  const detail = useLoad(
    async () => {
      const result = await api.rag.getSource(row.id);
      const busy = result.status === 'pending' || result.status === 'processing';
      setPollMs(busy ? POLL_MS : null);
      return result;
    },
    [row.id],
    { pollMs, fallbackError: 'Could not load this source.' }
  );
  const source = detail.data ?? row;
  const status = styleOf(RAG_SOURCE_STATUS, source.status);
  const busy = source.status === 'pending' || source.status === 'processing';
  const latest = detail.data?.jobs[0] ?? source.latest_job;

  async function act(kind: 'reindex' | 'retry', job?: EmbeddingJob | null) {
    setActing(true);
    try {
      if (kind === 'retry' && job) await api.rag.retryJob(job.id);
      else await api.rag.reindexSource(source.id);
      toast.success(kind === 'retry' ? 'Trying again' : 'Reindexing', {
        description: source.name,
      });
      setPollMs(POLL_MS);
      onChanged();
      void detail.reload();
    } catch (err) {
      toast.error(kind === 'retry' ? 'Could not retry' : 'Could not reindex', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setActing(false);
    }
  }

  const origin = sourceOrigin(source);

  return (
    <>
      <DialogHeader>
        <DialogTitle className="pr-6 break-words">{source.name}</DialogTitle>
        <DialogDescription className="flex flex-wrap items-center gap-2">
          <StatusPill tone={status.tone} pulse={status.pulse}>
            {status.label}
          </StatusPill>
          <span>{RAG_SOURCE_TYPE[source.source_type] ?? source.source_type}</span>
        </DialogDescription>
      </DialogHeader>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
        <Meta label="Passages" value={source.chunk_count.toLocaleString()} />
        <Meta
          label="Last embedded"
          value={source.last_indexed_at ? formatRelative(source.last_indexed_at) : 'Not yet'}
        />
        <Meta label="Added" value={formatDateTime(source.created_at)} />
        {source.size_bytes !== null && <Meta label="Size" value={formatBytes(source.size_bytes)} />}
        <Meta
          label="Embedding model"
          value={<span className="font-mono text-xs break-all">{source.embedding_model}</span>}
          className="col-span-2"
        />
        {origin && (
          <Meta
            label={source.source_type === 'link' ? 'Start page' : 'From'}
            className="col-span-2 sm:col-span-3"
            value={
              source.source_url ? (
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-primary inline-flex items-center gap-1 break-all underline underline-offset-2"
                >
                  {source.source_url}
                  <ExternalLinkIcon className="size-3.5 shrink-0" aria-hidden="true" />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              ) : (
                origin
              )
            }
          />
        )}
      </dl>

      {(source.error || latest?.status === 'failed') && (
        <div
          role="alert"
          className="bg-destructive/8 text-destructive grid gap-2 rounded-md p-3 text-sm"
        >
          <p className="font-medium">What went wrong</p>
          <p className="break-words whitespace-pre-line">
            {source.error ?? latest?.error ?? 'The last job failed without a message.'}
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {latest?.status === 'failed' ? (
          <Button size="sm" onClick={() => void act('retry', latest)} disabled={acting || busy}>
            {acting ? (
              <Loader2Icon className="animate-spin" aria-hidden="true" />
            ) : (
              <RotateCcwIcon aria-hidden="true" />
            )}
            Try again
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void act('reindex')}
            disabled={acting || busy}
          >
            {acting ? (
              <Loader2Icon className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCwIcon aria-hidden="true" />
            )}
            Reindex
          </Button>
        )}
      </div>

      {detail.error && !detail.data ? (
        <TableState error={detail.error} onRetry={() => void detail.retry()} rows={3} />
      ) : detail.loading && !detail.data ? (
        <TableState loading rows={3} />
      ) : detail.data ? (
        <>
          {detail.data.content && (
            <Section title="Text">
              <pre className="bg-muted/50 max-h-64 overflow-auto rounded-md border p-3 font-sans text-sm whitespace-pre-wrap">
                {detail.data.content}
              </pre>
            </Section>
          )}

          {source.source_type === 'link' && (
            <Section title={`Pages read (${detail.data.pages.length})`}>
              {detail.data.pages.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  {busy ? 'Crawling… pages appear here as they are read.' : 'No pages were read.'}
                </p>
              ) : (
                <ul className="max-h-72 divide-y overflow-y-auto rounded-md border">
                  {detail.data.pages.map((page) => {
                    const ps = styleOf(RAG_PAGE_STATUS, page.status);
                    return (
                      <li key={page.id} className="flex items-start gap-3 px-3 py-2 text-sm">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">
                            {page.title || page.url}
                          </span>
                          <a
                            href={page.url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="text-muted-foreground hover:text-foreground block truncate text-xs underline-offset-2 hover:underline"
                          >
                            {page.url}
                          </a>
                          {page.error && (
                            <span className="text-destructive block text-xs">{page.error}</span>
                          )}
                        </span>
                        <span className="flex shrink-0 flex-col items-end gap-1">
                          <StatusPill tone={ps.tone} pulse={ps.pulse}>
                            {ps.label}
                          </StatusPill>
                          <span className="text-muted-foreground text-xs tabular-nums">
                            {page.chunk_count} passages
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Section>
          )}

          {detail.data.jobs.length > 0 && (
            <Section title="Recent jobs">
              <ul className="divide-y rounded-md border">
                {detail.data.jobs.map((job) => {
                  const js = styleOf(JOB_STATUS, job.status);
                  return (
                    <li key={job.id} className="flex items-start gap-3 px-3 py-2 text-sm">
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">
                          {JOB_TYPE[job.job_type] ?? job.job_type}
                        </span>
                        <span className="text-muted-foreground block text-xs">
                          {formatDateTime(job.created_at)}
                          {job.attempts > 1 ? `, attempt ${job.attempts}` : ''}
                        </span>
                        {job.error && (
                          <span className="text-destructive block text-xs break-words">
                            {job.error}
                          </span>
                        )}
                      </span>
                      <StatusPill tone={js.tone} pulse={js.pulse}>
                        {js.label}
                      </StatusPill>
                    </li>
                  );
                })}
              </ul>
            </Section>
          )}
        </>
      ) : null}
    </>
  );
}

function Meta({
  label,
  value,
  className,
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5 tabular-nums">{value}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}
