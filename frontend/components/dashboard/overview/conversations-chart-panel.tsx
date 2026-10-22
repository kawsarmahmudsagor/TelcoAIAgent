'use client';

import { useState } from 'react';
import { AreaChart } from '@/components/dashboard/area-chart';
import { SectionCard } from '@/components/dashboard/section-card';
import { TableState } from '@/components/dashboard/table-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useLoad } from '@/hooks/useLoad';
import { type SeriesRange, api } from '@/lib/api-client';
import { formatShortDay } from '@/lib/format';
import { cn } from '@/lib/shadcn/utils';

const RANGES: { value: SeriesRange; label: string; long: string }[] = [
  { value: '7d', label: '7 days', long: 'the last 7 days' },
  { value: '30d', label: '30 days', long: 'the last 30 days' },
  { value: '90d', label: '90 days', long: 'the last 90 days' },
];

export function ConversationsChartPanel({ className }: { className?: string }) {
  const [range, setRange] = useState<SeriesRange>('7d');
  const { data, error, loading, retry } = useLoad(
    () => api.dashboard.conversationSeries(range),
    [range],
    { fallbackError: 'Could not load the conversation chart.' }
  );
  const current = RANGES.find((r) => r.value === range)!;
  // Keep showing the previous range's data while the next one loads, so the card doesn't jump.
  const series = data && !error ? data : undefined;

  return (
    <SectionCard
      className={className}
      title="Conversations"
      description={
        series ? (
          <>
            <span className="text-foreground font-display text-xl font-semibold tabular-nums">
              {series.total}
            </span>{' '}
            in {current.long}
          </>
        ) : (
          <>Chats and calls per day</>
        )
      }
      action={
        <div
          role="radiogroup"
          aria-label="Time range"
          className="bg-muted inline-flex rounded-md p-0.5"
        >
          {RANGES.map((r) => (
            <button
              key={r.value}
              type="button"
              role="radio"
              aria-checked={range === r.value}
              onClick={() => setRange(r.value)}
              className={cn(
                'focus-visible:ring-ring/50 h-7 rounded-[5px] px-2.5 text-xs font-medium outline-none focus-visible:ring-[3px]',
                range === r.value
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      }
    >
      {error ? (
        <TableState error={error} onRetry={() => void retry()} />
      ) : loading && !series ? (
        <Skeleton className="aspect-[640/220] w-full" />
      ) : series ? (
        <>
          <AreaChart
            points={series.points.map((p) => ({ label: formatShortDay(p.date), value: p.count }))}
            ariaLabel={`Conversations per day over ${current.long}: ${series.total} in total.`}
            unit={['conversation', 'conversations']}
            className={cn(loading && 'opacity-60')}
          />
          <p className="text-muted-foreground mt-2 text-xs">Days in {series.timezone} time.</p>
        </>
      ) : null}
    </SectionCard>
  );
}
