'use client';

import { useState } from 'react';
import { Loader2Icon, SearchIcon } from 'lucide-react';
import { FormField } from '@/components/dashboard/form-field';
import { SectionCard } from '@/components/dashboard/section-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { type RagSearchResponse, api } from '@/lib/api-client';
import { cn } from '@/lib/shadcn/utils';

/** Ask what a customer would ask and see which passages the agent would get, with scores. */
export function RetrievalTester({
  className,
  disabled,
}: {
  className?: string;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState('');
  const [threshold, setThreshold] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RagSearchResponse | null>(null);
  const [asked, setAsked] = useState('');

  async function search(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setBusy(true);
    setError(null);
    try {
      const k = topK.trim() ? Number(topK) : null;
      const t = threshold.trim() ? Number(threshold) : null;
      const response = await api.rag.search({
        query: q,
        top_k: k !== null && Number.isFinite(k) ? k : null,
        threshold: t !== null && Number.isFinite(t) ? t : null,
      });
      setResult(response);
      setAsked(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The search failed.');
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <SectionCard
      className={className}
      title="Try a question"
      description="See which passages the agent would read for a customer’s question. Uses the agent’s settings unless you override them here."
    >
      <form onSubmit={search} className="grid gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <label htmlFor="rag-query" className="sr-only">
            Question
          </label>
          <Input
            id="rag-query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Is there a service charge for flats in Gulshan?"
            maxLength={2000}
            disabled={disabled}
            className="flex-1"
          />
          <Button type="submit" disabled={busy || disabled || !query.trim()}>
            {busy ? (
              <Loader2Icon className="animate-spin" aria-hidden="true" />
            ) : (
              <SearchIcon aria-hidden="true" />
            )}
            Search
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:max-w-sm">
          <FormField id="rag-topk" label="Passages">
            {(control) => (
              <Input
                {...control}
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
                placeholder="Agent’s"
                disabled={disabled}
              />
            )}
          </FormField>
          <FormField id="rag-threshold" label="Min. score">
            {(control) => (
              <Input
                {...control}
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                placeholder="Agent’s"
                disabled={disabled}
              />
            )}
          </FormField>
        </div>
      </form>

      {error && (
        <p
          className="bg-destructive/8 text-destructive mt-4 rounded-md px-3 py-2 text-sm"
          role="alert"
        >
          {error}
        </p>
      )}

      {result && (
        <div className="mt-5 grid gap-3" aria-live="polite">
          <p className="text-muted-foreground text-sm">
            {result.results.length === 0
              ? `Nothing scored ${result.threshold.toFixed(2)} or higher for “${asked}”. Try a lower minimum score, or add a source that answers it.`
              : `${result.results.length} ${result.results.length === 1 ? 'passage' : 'passages'} for “${asked}”, best first. Minimum score ${result.threshold.toFixed(2)}.`}
          </p>
          <ol className="grid gap-3">
            {result.results.map((hit, i) => (
              <Hit key={i} rank={i + 1} hit={hit} threshold={result.threshold} />
            ))}
          </ol>
        </div>
      )}
    </SectionCard>
  );
}

function Hit({
  rank,
  hit,
  threshold,
}: {
  rank: number;
  hit: RagSearchResponse['results'][number];
  threshold: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const score = hit.score ?? 0;
  const long = hit.text.length > 320;
  return (
    <li className="rounded-md border p-3">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <span className="text-muted-foreground tabular-nums">#{rank}</span>
        <span className="min-w-0 flex-1 truncate font-medium">
          {hit.rag_source_name ?? 'Unknown source'}
        </span>
        <span className="flex items-center gap-2">
          {/* The bar spans 0.4..1, where nearly all scores land, so differences are visible. */}
          <span
            className="bg-muted relative h-1.5 w-20 overflow-hidden rounded-full"
            aria-hidden="true"
          >
            <span
              className={cn(
                'absolute inset-y-0 left-0 rounded-full',
                score >= threshold + 0.1 ? 'bg-success' : 'bg-warning'
              )}
              style={{ width: `${Math.max(0, Math.min(1, (score - 0.4) / 0.6)) * 100}%` }}
            />
          </span>
          <span className="font-medium tabular-nums">
            {hit.score === null ? 'n/a' : score.toFixed(3)}
          </span>
        </span>
      </div>
      <p
        className={cn(
          'text-sm leading-relaxed whitespace-pre-line',
          long && !expanded && 'line-clamp-4'
        )}
      >
        {hit.text}
      </p>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-primary mt-1 text-xs font-medium underline-offset-2 hover:underline"
          aria-expanded={expanded}
        >
          {expanded ? 'Show less' : 'Show all'}
        </button>
      )}
    </li>
  );
}
