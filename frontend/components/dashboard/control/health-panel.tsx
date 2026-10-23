import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import type { Overview } from '@/lib/types/admin';

function percent(rate: number | null): string {
  return rate === null ? '—' : `${Math.round(rate * 1000) / 10}%`;
}

function seconds(s: number | null): string {
  return s === null ? '—' : `${s.toFixed(1)} s`;
}

/** The overview's service indicators; a missing figure (nothing to measure yet) shows as "—". */
export function HealthPanel({ health }: { health: Overview['health'] }) {
  const rows = [
    {
      label: 'Recharge success rate',
      note: 'Last 24 hours',
      value: percent(health.recharge_success_rate_24h),
      bar: health.recharge_success_rate_24h,
    },
    {
      label: 'Median first response',
      note: 'AI agent, last 24 hours',
      value: seconds(health.median_first_response_s),
      bar: null,
    },
    {
      label: 'Active incidents',
      note: 'Network status',
      value: String(health.active_incidents),
      bar: null,
    },
    {
      label: 'Pending transactions',
      note: 'Waiting on the payment gateway',
      value: String(health.pending_transactions),
      bar: null,
    },
  ];
  return (
    <Panel>
      <PanelHeader title="Platform health" description="Key service indicators" />
      <dl className="space-y-3.5">
        {rows.map((r) => (
          <div key={r.label}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <dt className="text-xs font-bold">{r.label}</dt>
                <p className="text-muted-foreground text-[11px]">{r.note}</p>
              </div>
              <dd className="text-sm font-extrabold tabular-nums">{r.value}</dd>
            </div>
            {r.bar !== null && (
              <div
                className="bg-surface2 mt-2 h-1.5 overflow-hidden rounded-full"
                aria-hidden="true"
              >
                <span
                  className="bg-mint block h-full rounded-full"
                  style={{ width: `${Math.round(r.bar * 100)}%` }}
                />
              </div>
            )}
          </div>
        ))}
      </dl>
    </Panel>
  );
}
