'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { CircleAlertIcon, PlusIcon } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { PageHeader } from '@/components/dashboard/page-header';
import { Panel, TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useLoad } from '@/hooks/useLoad';
import { type RagSource, type RagSourceType, api } from '@/lib/api-client';
import { AddSourceDialog } from './add-source-dialog';
import { PropertiesSyncCard } from './properties-sync-card';
import { RetrievalTester } from './retrieval-tester';
import { SourceDetailDialog } from './source-detail-dialog';
import { SourceTable } from './source-table';

type Filter = 'all' | RagSourceType;

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'document', label: 'Documents' },
  { value: 'link', label: 'Websites' },
  { value: 'text', label: 'Text' },
  { value: 'properties', label: 'Listings' },
];

const POLL_MS = 3000;

export function isBusy(source: RagSource) {
  return source.status === 'pending' || source.status === 'processing';
}

export function KnowledgeView() {
  const [filter, setFilter] = useState<Filter>('all');
  const [adding, setAdding] = useState(false);
  const [viewing, setViewing] = useState<RagSource | null>(null);
  const [deleting, setDeleting] = useState<RagSource | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [pollMs, setPollMs] = useState<number | null>(null);

  const sources = useLoad(
    async () => {
      const page = await api.rag.sources({ limit: 500 });
      // Keep polling only while something is still being embedded.
      setPollMs(page.items.some(isBusy) ? POLL_MS : null);
      return page.items;
    },
    [],
    { pollMs, fallbackError: 'Could not load knowledge sources.' }
  );
  const status = useLoad(() => api.dashboard.ragStatus(), [], { pollMs });

  const all = useMemo(() => sources.data ?? [], [sources.data]);
  const counts = useMemo(() => {
    const result: Record<Filter, number> = {
      all: all.length,
      document: 0,
      link: 0,
      text: 0,
      properties: 0,
    };
    for (const s of all) result[s.source_type] = (result[s.source_type] ?? 0) + 1;
    return result;
  }, [all]);
  const shown = filter === 'all' ? all : all.filter((s) => s.source_type === filter);
  const propertiesSource = all.find((s) => s.source_type === 'properties') ?? null;
  const embeddingReady = status.data?.embedding_ready ?? true;

  function refreshSoon() {
    setPollMs(POLL_MS);
    void sources.reload();
    void status.reload();
  }

  async function reindex(source: RagSource) {
    try {
      await api.rag.reindexSource(source.id);
      toast.success('Reindexing', { description: source.name });
      refreshSoon();
    } catch (err) {
      toast.error('Could not reindex', {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  async function retry(source: RagSource) {
    if (!source.latest_job) return reindex(source);
    try {
      await api.rag.retryJob(source.latest_job.id);
      toast.success('Trying again', { description: source.name });
      refreshSoon();
    } catch (err) {
      toast.error('Could not retry', {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.rag.deleteSource(deleting.id);
      toast.success('Source deleted', { description: deleting.name });
      setDeleting(null);
      refreshSoon();
    } catch (err) {
      toast.error('Could not delete the source', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Knowledge base"
        description="Documents, web pages and notes the agent can search to answer questions."
        actions={
          <Button onClick={() => setAdding(true)} disabled={!embeddingReady}>
            <PlusIcon aria-hidden="true" />
            Add source
          </Button>
        }
      />

      {!embeddingReady && (
        <div
          role="alert"
          className="border-destructive/30 bg-destructive/8 text-destructive mb-6 flex gap-3 rounded-lg border p-4 text-sm"
        >
          <CircleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>
            <span className="font-medium">Nothing can be added or searched yet.</span> Embeddings
            need an OpenRouter key: set OPENROUTER_API_KEY on the server, or save an OpenRouter key
            on the{' '}
            <Link href="/dashboard/chatbot?tab=model" className="underline underline-offset-2">
              Chatbot page
            </Link>
            .
          </p>
        </div>
      )}
      {status.data && !status.data.rag_enabled && embeddingReady && (
        <p className="bg-muted text-muted-foreground mb-6 rounded-lg px-4 py-3 text-sm">
          The agent isn’t using the knowledge base right now. Turn it on in the{' '}
          <Link
            href="/dashboard/chatbot?tab=knowledge"
            className="text-primary underline underline-offset-2"
          >
            Chatbot settings
          </Link>
          .
        </p>
      )}

      <div className="space-y-6">
        <section aria-labelledby="sources-heading" className="space-y-3">
          <h2 id="sources-heading" className="sr-only">
            Sources
          </h2>
          <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
              <TabsList>
                {FILTERS.map((f) => (
                  <TabsTrigger key={f.value} value={f.value} className="px-3">
                    {f.label}
                    <span className="text-muted-foreground text-xs tabular-nums">
                      {counts[f.value]}
                    </span>
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>
          <Panel>
            {sources.loading || sources.error || shown.length === 0 ? (
              <TableState
                loading={sources.loading}
                error={sources.error}
                onRetry={() => void sources.retry()}
                empty={
                  filter === 'all' ? (
                    <>
                      <p className="text-foreground font-medium">The knowledge base is empty</p>
                      <p className="max-w-md">
                        Add your FAQ, price lists or building rules so the agent can answer from
                        them instead of guessing.
                      </p>
                      <Button
                        size="sm"
                        className="mt-1"
                        onClick={() => setAdding(true)}
                        disabled={!embeddingReady}
                      >
                        <PlusIcon aria-hidden="true" />
                        Add source
                      </Button>
                    </>
                  ) : (
                    <p>No {FILTERS.find((f) => f.value === filter)?.label.toLowerCase()} yet.</p>
                  )
                }
              />
            ) : (
              <SourceTable
                sources={shown}
                onView={setViewing}
                onReindex={(s) => void reindex(s)}
                onRetry={(s) => void retry(s)}
                onDelete={setDeleting}
              />
            )}
          </Panel>
        </section>

        <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
          <RetrievalTester className="lg:col-span-2" disabled={!embeddingReady} />
          <PropertiesSyncCard
            source={propertiesSource}
            loading={sources.loading}
            disabled={!embeddingReady}
            onSynced={refreshSoon}
          />
        </div>
      </div>

      <AddSourceDialog open={adding} onOpenChange={setAdding} onCreated={refreshSoon} />
      <SourceDetailDialog
        source={viewing}
        onOpenChange={(open) => !open && setViewing(null)}
        onChanged={refreshSoon}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this source?"
        description={
          <>
            <span className="text-foreground font-medium">{deleting?.name}</span> and its{' '}
            {deleting?.chunk_count ?? 0} passages are removed, and the agent stops using them. This
            can’t be undone.
          </>
        }
        confirmLabel="Delete source"
        onConfirm={confirmDelete}
        busy={deleteBusy}
      />
    </>
  );
}
