'use client';

import { useState } from 'react';
import Link from 'next/link';
import { CircleAlertIcon, Loader2Icon, RefreshCwIcon } from 'lucide-react';
import { toast } from 'sonner';
import { FormField } from '@/components/dashboard/form-field';
import { SectionCard } from '@/components/dashboard/section-card';
import { StatusPill } from '@/components/dashboard/status-pill';
import { RAG_SOURCE_STATUS, RAG_SOURCE_TYPE, styleOf } from '@/components/dashboard/status-tones';
import { SwitchRow } from '@/components/dashboard/switch-row';
import { TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import type { LoadState } from '@/hooks/useLoad';
import { type AgentConfigOptions, type RagSource, api } from '@/lib/api-client';
import { cn } from '@/lib/shadcn/utils';
import { EmbeddingModelField } from './embedding-model-field';
import type { ConfigDraftApi } from './use-config-draft';

export function KnowledgeTab({
  form,
  options,
  sources,
}: {
  form: ConfigDraftApi;
  options: AgentConfigOptions;
  sources: LoadState<RagSource[]>;
}) {
  const { draft, saved, errors, set, accept } = form;
  const [reindexing, setReindexing] = useState(false);
  const staleCount = sources.data?.filter((s) => s.status === 'stale').length ?? 0;
  const chunkingEdited =
    draft.chunk_size !== String(saved.chunk_size) ||
    draft.chunk_overlap !== String(saved.chunk_overlap);

  async function reindexAll() {
    setReindexing(true);
    try {
      const { queued } = await api.rag.reindexAll();
      toast.success(queued ? `Reindexing ${queued} sources` : 'Nothing to reindex', {
        description: queued ? 'Progress shows on the Knowledge base page.' : undefined,
      });
      void sources.reload();
    } catch (err) {
      toast.error('Could not start reindexing', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setReindexing(false);
    }
  }

  return (
    <div className="grid gap-4 sm:gap-6">
      {!saved.embedding_ready && (
        <div
          role="alert"
          className="border-destructive/30 bg-destructive/8 text-destructive flex gap-3 rounded-lg border p-4 text-sm"
        >
          <CircleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium">The knowledge base can’t work without an OpenRouter key</p>
            <p className="mt-1">
              Embeddings go through OpenRouter. Set OPENROUTER_API_KEY on the server, or choose
              OpenRouter on the Model and voice tab and save a key there. Until then nothing can be
              added or searched.
            </p>
          </div>
        </div>
      )}

      <SectionCard
        title="Answers from the knowledge base"
        description="Lets the agent look things up in your documents, website pages and listings before it answers."
      >
        <SwitchRow
          label="Use the knowledge base"
          description="When off, the agent answers from its instructions and the listings search only."
          checked={draft.rag_enabled}
          onCheckedChange={(value) => set('rag_enabled', value)}
          className="pt-0"
        />
        <div
          className={cn(
            'mt-2 grid gap-6 border-t pt-5 sm:grid-cols-2',
            !draft.rag_enabled && 'opacity-60'
          )}
        >
          <SliderField
            id="rag_top_k"
            label="Passages per lookup"
            value={draft.rag_top_k}
            display={String(draft.rag_top_k)}
            min={1}
            max={20}
            step={1}
            onChange={(v) => set('rag_top_k', v)}
            disabled={!draft.rag_enabled}
            hint="How many matching passages the agent reads each time it searches. 3 to 6 suits most FAQs."
            error={errors.rag_top_k}
          />
          <SliderField
            id="rag_similarity_threshold"
            label="Minimum match score"
            value={draft.rag_similarity_threshold}
            display={draft.rag_similarity_threshold.toFixed(2)}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => set('rag_similarity_threshold', v)}
            disabled={!draft.rag_enabled}
            error={errors.rag_similarity_threshold}
            hint={
              <>
                Passages scoring below this are ignored. Scores are cosine similarity from 0 to 1,
                and unrelated text often still scores around 0.6, so useful values are roughly 0.6
                to 0.8. Try a question in the retrieval tester on the{' '}
                <Link href="/dashboard/knowledge" className="underline underline-offset-2">
                  Knowledge base page
                </Link>{' '}
                to see real scores.
              </>
            }
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Sources the agent may search"
        description="Limit the agent to some sources, for example while a new one is being checked."
      >
        <SourceScope
          sources={sources}
          selected={draft.rag_source_ids}
          onChange={(ids) => set('rag_source_ids', ids)}
          disabled={!draft.rag_enabled}
          error={errors.rag_source_ids}
        />
      </SectionCard>

      <SectionCard
        title="Embedding and chunking"
        description="How documents are cut into passages and turned into vectors."
      >
        <div className="grid gap-6">
          <EmbeddingModelField
            config={saved}
            models={options.embedding_models}
            onConfig={accept}
            disabled={!saved.embedding_ready}
          />
          <div className="grid gap-4 border-t pt-5 sm:grid-cols-2">
            <FormField
              id="chunk_size"
              label="Passage size (tokens)"
              error={errors.chunk_size}
              hint="64 to 4,096. Smaller passages match precise questions better."
            >
              {(control) => (
                <Input
                  {...control}
                  type="number"
                  inputMode="numeric"
                  min={64}
                  max={4096}
                  value={draft.chunk_size}
                  onChange={(e) => set('chunk_size', e.target.value)}
                />
              )}
            </FormField>
            <FormField
              id="chunk_overlap"
              label="Overlap (tokens)"
              error={errors.chunk_overlap}
              hint="Text shared by neighbouring passages, so a sentence isn't cut in half."
            >
              {(control) => (
                <Input
                  {...control}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={1024}
                  value={draft.chunk_overlap}
                  onChange={(e) => set('chunk_overlap', e.target.value)}
                />
              )}
            </FormField>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
            <p className="text-muted-foreground min-w-0 flex-1 text-sm">
              {chunkingEdited
                ? 'After you save, existing sources are marked “Needs reindex” until they are cut again.'
                : staleCount > 0
                  ? `${staleCount} ${staleCount === 1 ? 'source was' : 'sources were'} cut with older settings and still work, but should be reindexed.`
                  : 'Every source uses the current settings.'}
            </p>
            <Button
              type="button"
              variant={staleCount > 0 ? 'default' : 'outline'}
              size="sm"
              onClick={() => void reindexAll()}
              disabled={reindexing || chunkingEdited || !saved.embedding_ready}
              title={chunkingEdited ? 'Save the new settings first' : undefined}
            >
              {reindexing ? (
                <Loader2Icon className="animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCwIcon aria-hidden="true" />
              )}
              Reindex all
            </Button>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}

function SliderField({
  id,
  label,
  value,
  display,
  min,
  max,
  step,
  onChange,
  disabled,
  hint,
  error,
}: {
  id: string;
  label: string;
  value: number;
  display: string;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  hint: React.ReactNode;
  error?: string;
}) {
  return (
    <FormField
      id={id}
      label={label}
      hint={hint}
      error={error}
      aside={
        <span className="font-display text-base font-semibold tabular-nums" aria-hidden="true">
          {display}
        </span>
      }
    >
      {(control) => (
        <Slider
          id={id}
          value={[value]}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onValueChange={([v]) => onChange(v)}
          aria-label={label}
          aria-describedby={control['aria-describedby']}
          className="py-2"
        />
      )}
    </FormField>
  );
}

function SourceScope({
  sources,
  selected,
  onChange,
  disabled,
  error,
}: {
  sources: LoadState<RagSource[]>;
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled: boolean;
  error?: string;
}) {
  const all = selected.length === 0;
  const [limiting, setLimiting] = useState(!all);
  const showList = limiting || !all;

  if (sources.loading || sources.error) {
    return (
      <TableState
        loading={sources.loading}
        error={sources.error}
        onRetry={() => void sources.retry()}
        rows={2}
      />
    );
  }
  const list = sources.data ?? [];

  function toggle(id: string) {
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }

  return (
    <fieldset disabled={disabled} className="grid gap-3">
      <legend className="sr-only">Sources the agent may search</legend>
      <div role="radiogroup" className="grid gap-2 sm:grid-cols-2">
        <ScopeOption
          checked={!showList}
          onSelect={() => {
            setLimiting(false);
            onChange([]);
          }}
          title="All ready sources"
          description="New sources are included as soon as they are ready."
        />
        <ScopeOption
          checked={showList}
          onSelect={() => setLimiting(true)}
          title="Only the ones I pick"
          description="New sources stay out until you tick them."
        />
      </div>

      {showList &&
        (list.length === 0 ? (
          <p className="text-muted-foreground rounded-md border border-dashed p-4 text-sm">
            No sources yet.{' '}
            <Link href="/dashboard/knowledge" className="text-primary underline underline-offset-2">
              Add one on the Knowledge base page
            </Link>
            .
          </p>
        ) : (
          <ul className="max-h-72 divide-y overflow-y-auto rounded-md border">
            {list.map((source) => {
              const status = styleOf(RAG_SOURCE_STATUS, source.status);
              const inputId = `scope-${source.id}`;
              return (
                <li key={source.id} className="flex items-center gap-3 px-3 py-2.5">
                  <Checkbox
                    id={inputId}
                    checked={selected.includes(source.id)}
                    onCheckedChange={() => toggle(source.id)}
                  />
                  <label htmlFor={inputId} className="min-w-0 flex-1 cursor-pointer text-sm">
                    <span className="block truncate font-medium">{source.name}</span>
                    <span className="text-muted-foreground block text-xs">
                      {RAG_SOURCE_TYPE[source.source_type] ?? source.source_type}
                    </span>
                  </label>
                  {source.status !== 'ready' && (
                    <StatusPill tone={status.tone}>{status.label}</StatusPill>
                  )}
                </li>
              );
            })}
          </ul>
        ))}
      {showList && selected.length === 0 && list.length > 0 && (
        <p className="text-warning text-xs">
          Nothing ticked yet: until you tick a source, the agent still searches all of them.
        </p>
      )}
      {error && (
        <p className="text-destructive text-xs" role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}

function ScopeOption({
  checked,
  onSelect,
  title,
  description,
}: {
  checked: boolean;
  onSelect: () => void;
  title: string;
  description: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      onClick={onSelect}
      className={cn(
        'focus-visible:ring-ring/50 flex gap-3 rounded-md border p-3 text-left outline-none focus-visible:ring-[3px] disabled:opacity-60',
        checked ? 'border-primary bg-primary/5' : 'hover:bg-accent/50'
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border',
          checked ? 'border-primary' : 'border-input'
        )}
      >
        {checked && <span className="bg-primary size-2 rounded-full" />}
      </span>
      <span>
        <span className="block text-sm font-medium">{title}</span>
        <span className="text-muted-foreground block text-xs">{description}</span>
      </span>
    </button>
  );
}
