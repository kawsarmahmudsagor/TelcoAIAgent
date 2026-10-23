'use client';

import { useState } from 'react';
import {
  AlertCircleIcon,
  BanknoteIcon,
  CheckCircle2Icon,
  ClockIcon,
  ReceiptTextIcon,
} from 'lucide-react';
import { FIELD, SearchField, SegmentedFilter } from '@/components/dashboard/list-controls';
import { Pager } from '@/components/dashboard/pager';
import { TxnTable } from '@/components/dashboard/transactions/txn-table';
import { useUrlParams } from '@/components/dashboard/use-url-param';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { adminApi } from '@/lib/admin-api';
import { useAdminQuery } from '@/lib/admin-query';
import { cn } from '@/lib/shadcn/utils';
import { formatTaka } from '@/lib/telco-format';
import type { TransactionListParams } from '@/lib/types/admin';
import type { TxnStatus, TxnType } from '@/lib/types/portal';

const PAGE_SIZE = 25;
/** How far back the list reaches (the API allows up to 90). */
const DAYS = 30;
const nf = new Intl.NumberFormat('en-IN');

type StatusFilter = TxnStatus | 'all';
const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'success', label: 'Success' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
];
const TYPES: TxnType[] = ['recharge', 'purchase', 'redeem'];
const TYPE_LABEL: Record<TxnType, string> = {
  recharge: 'Recharges',
  purchase: 'Packages',
  redeem: 'Redemptions',
};

export function TransactionsView() {
  const [params, setParams] = useUrlParams();
  const rawStatus = params.get('status');
  const status = STATUS_OPTIONS.find((o) => o.value !== 'all' && o.value === rawStatus)?.value as
    | TxnStatus
    | undefined;
  const type = TYPES.find((t) => t === params.get('type'));

  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);

  const query: TransactionListParams = {
    status,
    type,
    q: q || undefined,
    days: DAYS,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };
  const { data, error, loading, reload } = useAdminQuery(
    'transactions',
    () => adminApi.transactions(query),
    [status, type, q, page]
  );
  const stats = useAdminQuery('txnStats', () => adminApi.transactionStats());
  const s = stats.data;

  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] text-[25px] font-bold tracking-[-0.8px]">Transactions</h1>
        <p className="text-muted-foreground mt-1 text-xs">
          Recharges, package purchases and redemptions, with failure reasons. Phone numbers are
          masked in this view.
        </p>
      </div>

      <div className="tablet:grid-cols-2 mb-4 grid grid-cols-4 gap-4">
        <MetricTile
          icon={BanknoteIcon}
          tone="purple"
          label="Today's volume"
          value={s ? formatTaka(s.volume) : <Bone className="h-7 w-24" />}
          foot={s && `${nf.format(s.attempts)} ${s.attempts === 1 ? 'attempt' : 'attempts'}`}
        />
        <MetricTile
          icon={CheckCircle2Icon}
          tone="green"
          label="Successful"
          value={s ? nf.format(s.success) : <Bone className="h-7 w-16" />}
          foot={
            s &&
            (s.success_rate === null
              ? 'No finished payments yet'
              : `${Math.round(s.success_rate * 1000) / 10}% success rate`)
          }
        />
        <MetricTile
          icon={ClockIcon}
          tone="orange"
          label="Pending"
          value={s ? nf.format(s.pending) : <Bone className="h-7 w-12" />}
          foot={s && 'Awaiting reconciliation'}
        />
        <MetricTile
          icon={AlertCircleIcon}
          tone="pink"
          label="Failed"
          value={s ? nf.format(s.failed) : <Bone className="h-7 w-12" />}
          foot={s && 'Review failure reasons'}
        />
      </div>

      <Panel>
        <PanelHeader
          title="Recent transactions"
          description={
            data
              ? `${nf.format(data.total)} ${data.total === 1 ? 'match' : 'matches'} in the last ${DAYS} days`
              : 'Loading…'
          }
        />
        <div className="tablet:flex-col tablet:items-stretch mb-4 flex items-center gap-2.5">
          <SearchField
            label="Search by reference or number"
            placeholder="Search reference or number…"
            onSearch={(text) => {
              setQ(text);
              setPage(0);
            }}
          />
          <SegmentedFilter
            label="Status"
            value={status ?? 'all'}
            options={STATUS_OPTIONS}
            onChange={(v) => {
              setParams({ status: v === 'all' ? null : v });
              setPage(0);
            }}
          />
          <label>
            <span className="sr-only">Type</span>
            <select
              value={type ?? ''}
              onChange={(e) => {
                setParams({ type: e.target.value || null });
                setPage(0);
              }}
              className={cn(FIELD, 'tablet:w-full')}
            >
              <option value="">All types</option>
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && !data ? (
          <LoadError what="Transactions" error={error} onRetry={reload} />
        ) : !data ? (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 5 }).map((_, i) => (
              <Bone key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : data.items.length === 0 ? (
          <div className="text-muted-foreground flex flex-col items-center gap-2 py-10 text-center text-xs">
            <ReceiptTextIcon className="size-6" aria-hidden="true" />
            <p>
              No transactions match. Try another status or type, or search a different reference.
            </p>
          </div>
        ) : (
          <div
            className={cn(loading && 'opacity-60 motion-safe:transition-opacity')}
            aria-busy={loading}
          >
            <TxnTable items={data.items} />
            <Pager page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
          </div>
        )}
      </Panel>
    </>
  );
}
