'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ChevronLeftIcon, ChevronRightIcon, SearchIcon, UsersIcon } from 'lucide-react';
import {
  Avatar,
  SubscriberStatusChip,
  balanceText,
} from '@/components/dashboard/subscribers/subscriber-parts';
import { SubscriberSheet } from '@/components/dashboard/subscribers/subscriber-sheet';
import { PortalButton } from '@/components/portal/ui/link-button';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { adminApi } from '@/lib/admin-api';
import { useAdminQuery } from '@/lib/admin-query';
import { cn } from '@/lib/shadcn/utils';
import { formatDay, formatPlan } from '@/lib/telco-format';
import type { SubscriberItem, SubscriberListParams } from '@/lib/types/admin';
import type { PlanType } from '@/lib/types/portal';

const PAGE_SIZE = 25;
const DEBOUNCE_MS = 300;

const FIELD =
  'border-line bg-surface text-foreground rounded-button focus-visible:ring-ring/60 min-h-9 border px-3 text-xs outline-none focus-visible:ring-[3px]';

export function SubscribersView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const openId = params.get('id');

  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [plan, setPlan] = useState<PlanType | ''>('');
  const [status, setStatus] = useState<SubscriberListParams['status'] | ''>('');
  const [page, setPage] = useState(0);

  // Wait for a pause in typing before querying, and start from the first page of the new results.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search.trim());
      setPage(0);
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [search]);

  const query: SubscriberListParams = {
    q: q || undefined,
    plan_type: plan || undefined,
    status: status || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };
  const { data, error, loading, reload } = useAdminQuery(
    'subscribers',
    () => adminApi.subscribers(query),
    [q, plan, status, page]
  );

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = Math.min(total, (page + 1) * PAGE_SIZE);

  function openSheet(id: string | null) {
    router.replace(id ? `${pathname}?id=${id}` : pathname, { scroll: false });
  }

  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] text-[25px] font-bold tracking-[-0.8px]">
          Subscriber directory
        </h1>
        <p className="text-muted-foreground mt-1 text-xs">
          Search and review subscriber accounts. Phone numbers are masked in this view.
        </p>
      </div>

      <Panel>
        <PanelHeader
          title="All subscribers"
          description={
            data
              ? `${total.toLocaleString('en-IN')} ${total === 1 ? 'match' : 'matches'}`
              : 'Loading…'
          }
        />
        <div className="phone:flex-col phone:items-stretch mb-4 flex items-center gap-2.5">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search by name or number</span>
            <SearchIcon
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2"
              aria-hidden="true"
            />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name or number…"
              className={cn(FIELD, 'w-full pl-9')}
            />
          </label>
          <div className="flex gap-2.5">
            <label className="flex-1">
              <span className="sr-only">Plan</span>
              <select
                value={plan}
                onChange={(e) => {
                  setPlan(e.target.value as PlanType | '');
                  setPage(0);
                }}
                className={cn(FIELD, 'w-full')}
              >
                <option value="">All plans</option>
                <option value="prepaid">Prepaid</option>
                <option value="postpaid">Postpaid</option>
              </select>
            </label>
            <label className="flex-1">
              <span className="sr-only">Status</span>
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value as typeof status);
                  setPage(0);
                }}
                className={cn(FIELD, 'w-full')}
              >
                <option value="">Any status</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
              </select>
            </label>
          </div>
        </div>

        {error && !data ? (
          <LoadError what="Subscribers" error={error} onRetry={reload} />
        ) : !data ? (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 5 }).map((_, i) => (
              <Bone key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : data.items.length === 0 ? (
          <div className="text-muted-foreground flex flex-col items-center gap-2 py-10 text-center text-xs">
            <UsersIcon className="size-6" aria-hidden="true" />
            <p>
              No subscribers match. Try a different name, the last digits of a number, or clear the
              filters.
            </p>
          </div>
        ) : (
          <div
            className={cn(loading && 'opacity-60 motion-safe:transition-opacity')}
            aria-busy={loading}
          >
            <SubscriberTable items={data.items} onView={openSheet} />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-muted-foreground text-[11px]" aria-live="polite">
                Showing {from}–{to} of {total.toLocaleString('en-IN')}
              </p>
              <div className="flex items-center gap-2">
                <PortalButton
                  variant="outline"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeftIcon aria-hidden="true" />
                  Previous
                </PortalButton>
                <span className="text-muted-foreground text-[11px] tabular-nums">
                  Page {page + 1} of {pages}
                </span>
                <PortalButton
                  variant="outline"
                  disabled={page + 1 >= pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                  <ChevronRightIcon aria-hidden="true" />
                </PortalButton>
              </div>
            </div>
          </div>
        )}
      </Panel>

      <SubscriberSheet id={openId} onClose={() => openSheet(null)} />
    </>
  );
}

function ViewButton({ item, onView }: { item: SubscriberItem; onView: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onView(item.id)}
      aria-label={`View ${item.full_name}`}
      className="text-brand focus-visible:ring-ring/60 dark:text-brand2 rounded-md p-[3px] text-[11px] font-bold outline-none hover:underline focus-visible:ring-[3px]"
    >
      View
    </button>
  );
}

function Person({ item }: { item: SubscriberItem }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <Avatar name={item.full_name} />
      <div className="min-w-0">
        <p className="truncate text-xs font-bold">{item.full_name}</p>
        <p className="text-muted-foreground truncate text-[11px]">{item.district}</p>
      </div>
    </div>
  );
}

/** A table, or stacked cards at 760px and below. */
function SubscriberTable({
  items,
  onView,
}: {
  items: SubscriberItem[];
  onView: (id: string) => void;
}) {
  return (
    <>
      <table className="tablet:hidden w-full border-collapse text-left">
        <caption className="sr-only">Subscribers, sorted by name</caption>
        <thead>
          <tr className="text-muted-foreground border-line border-b text-[11px]">
            {['Subscriber', 'Number', 'Plan', 'Balance', 'Status', 'Joined'].map((h) => (
              <th key={h} scope="col" className="py-2.5 pr-3 font-semibold whitespace-nowrap">
                {h}
              </th>
            ))}
            <th scope="col" className="py-2.5">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id} className="border-line border-b text-xs last:border-b-0">
              <td className="max-w-[240px] py-3 pr-3">
                <Person item={s} />
              </td>
              <td className="py-3 pr-3 whitespace-nowrap tabular-nums">{s.msisdn_masked}</td>
              <td className="py-3 pr-3">{formatPlan(s.plan_type)}</td>
              <td className="py-3 pr-3 whitespace-nowrap tabular-nums">{balanceText(s)}</td>
              <td className="py-3 pr-3">
                <SubscriberStatusChip status={s.status} />
              </td>
              <td className="py-3 pr-3 whitespace-nowrap">{formatDay(s.joined_on)}</td>
              <td className="py-3 text-right">
                <ViewButton item={s} onView={onView} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="tablet:block hidden">
        {items.map((s) => (
          <li
            key={s.id}
            className="border-line border-b py-3.5 first:pt-0 last:border-b-0 last:pb-0"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <Person item={s} />
              <SubscriberStatusChip status={s.status} />
            </div>
            <p className="text-muted-foreground text-[11px] tabular-nums">
              {s.msisdn_masked} · {formatPlan(s.plan_type)} · {balanceText(s)}
            </p>
            <div className="mt-1.5 flex items-center justify-between">
              <p className="text-muted-foreground text-[10px]">Joined {formatDay(s.joined_on)}</p>
              <ViewButton item={s} onView={onView} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
