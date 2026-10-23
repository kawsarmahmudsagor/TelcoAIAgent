'use client';

import { useState } from 'react';
import { BotIcon, CheckCheckIcon, LifeBuoyIcon, RotateCwIcon, TimerIcon } from 'lucide-react';
import { toast } from 'sonner';
import { CaseQueueTable } from '@/components/dashboard/cases/case-table';
import { SegmentedFilter } from '@/components/dashboard/list-controls';
import { Pager } from '@/components/dashboard/pager';
import { useUrlParams } from '@/components/dashboard/use-url-param';
import { PortalButton } from '@/components/portal/ui/link-button';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { adminApi } from '@/lib/admin-api';
import { invalidateAdmin, useAdminQuery } from '@/lib/admin-query';
import { ApiError } from '@/lib/api-client';
import { cn } from '@/lib/shadcn/utils';
import type { AdminCase, CaseListParams } from '@/lib/types/admin';
import type { CaseStatus } from '@/lib/types/portal';

const PAGE_SIZE = 25;
const nf = new Intl.NumberFormat('en-IN');

type QueueFilter = 'all' | 'high' | 'open';
const FILTERS: { value: QueueFilter; label: string }[] = [
  { value: 'all', label: 'All cases' },
  { value: 'high', label: 'High priority' },
  { value: 'open', label: 'Open' },
];

const DONE: Record<CaseStatus, string> = {
  open: 'reopened',
  in_review: 'moved to in review',
  resolved: 'resolved',
};

export function CasesView() {
  const [params, setParams] = useUrlParams();
  const filter: QueueFilter =
    params.get('priority') === 'high' ? 'high' : params.get('status') === 'open' ? 'open' : 'all';
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());

  const query: CaseListParams = {
    priority: filter === 'high' ? 'high' : undefined,
    open_only: filter === 'open' ? true : undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };
  const { data, error, loading, reload } = useAdminQuery('cases', () => adminApi.cases(query), [
    filter,
    page,
  ]);
  const stats = useAdminQuery('caseStats', () => adminApi.caseStats());
  const s = stats.data;

  async function change(c: AdminCase, status: CaseStatus) {
    if (busy.has(c.ref)) return;
    setBusy((prev) => new Set(prev).add(c.ref));
    try {
      await adminApi.setCaseStatus(c.ref, status);
      toast.success(`${c.ref} ${DONE[status]}`, {
        description: `${c.subscriber_name} will see the update in their portal.`,
      });
      invalidateAdmin(['cases', 'caseStats', 'overview']);
    } catch (e) {
      toast.error(`Could not update ${c.ref}`, {
        description: e instanceof ApiError ? e.message : 'Try again.',
      });
    } finally {
      setBusy((prev) => {
        const next = new Set(prev);
        next.delete(c.ref);
        return next;
      });
    }
  }

  function refresh() {
    invalidateAdmin(['cases', 'caseStats']);
  }

  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] text-[25px] font-bold tracking-[-0.8px]">Support queue</h1>
        <p className="text-muted-foreground mt-1 text-xs">
          Review subscriber issues. Changing a case&apos;s status notifies the subscriber.
        </p>
      </div>

      <div className="tablet:grid-cols-2 phone:grid-cols-1 mb-4 grid grid-cols-3 gap-4">
        <MetricTile
          icon={LifeBuoyIcon}
          tone="orange"
          label="Open cases"
          value={s ? nf.format(s.open) : <Bone className="h-7 w-12" />}
          badge={s && s.high_open > 0 && <StatusChip tone="failed">{s.high_open} high</StatusChip>}
          foot={s && `${nf.format(s.high_open)} high priority`}
        />
        <MetricTile
          icon={TimerIcon}
          tone="purple"
          label="Avg. resolution"
          value={
            s ? (
              s.avg_resolution_hours_7d === null ? (
                '—'
              ) : (
                `${s.avg_resolution_hours_7d} hrs`
              )
            ) : (
              <Bone className="h-7 w-16" />
            )
          }
          foot={
            s && (s.avg_resolution_hours_7d === null ? 'Nothing resolved this week' : 'Last 7 days')
          }
        />
        <MetricTile
          icon={BotIcon}
          tone="green"
          label="AI assisted"
          value={s ? `${Math.round(s.ai_assisted_share_7d * 100)}%` : <Bone className="h-7 w-16" />}
          foot={s && 'Cases opened by the assistant, last 7 days'}
        />
      </div>

      <Panel>
        <PanelHeader
          title="Priority cases"
          description={
            data
              ? `${nf.format(data.total)} ${data.total === 1 ? 'case' : 'cases'}, high priority first`
              : 'Loading…'
          }
        />
        <div className="phone:flex-col phone:items-stretch mb-4 flex flex-wrap items-center justify-between gap-2.5">
          <SegmentedFilter
            label="Show"
            value={filter}
            options={FILTERS}
            onChange={(v) => {
              setParams({
                priority: v === 'high' ? 'high' : null,
                status: v === 'open' ? 'open' : null,
              });
              setPage(0);
            }}
          />
          <PortalButton variant="outline" onClick={refresh} disabled={loading} aria-busy={loading}>
            <RotateCwIcon
              className={cn(loading && 'motion-safe:animate-spin')}
              aria-hidden="true"
            />
            Refresh
          </PortalButton>
        </div>

        {error && !data ? (
          <LoadError what="The support queue" error={error} onRetry={reload} />
        ) : !data ? (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 5 }).map((_, i) => (
              <Bone key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : data.items.length === 0 ? (
          <div className="text-muted-foreground flex flex-col items-center gap-2 py-10 text-center text-xs">
            <CheckCheckIcon className="size-6" aria-hidden="true" />
            <p>
              {filter === 'all'
                ? 'No cases yet. New ones from the portal and the assistant show up here.'
                : 'Nothing in this view. Switch to All cases to see the rest.'}
            </p>
          </div>
        ) : (
          <div
            className={cn(loading && 'opacity-60 motion-safe:transition-opacity')}
            aria-busy={loading}
          >
            <CaseQueueTable
              items={data.items}
              busy={busy}
              onChange={(c, st) => void change(c, st)}
            />
            <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
          </div>
        )}
      </Panel>
    </>
  );
}
