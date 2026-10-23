'use client';

import { BellIcon, InboxIcon } from 'lucide-react';
import { Avatar } from '@/components/dashboard/avatar';
import {
  SubscriberStatusChip,
  TxnStatusChip,
} from '@/components/dashboard/subscribers/subscriber-parts';
import { caseCategoryLabel } from '@/components/portal/support/case-categories';
import { CaseStatusChip } from '@/components/portal/support/case-table';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { adminApi } from '@/lib/admin-api';
import { useAdminQuery } from '@/lib/admin-query';
import {
  formatData,
  formatDay,
  formatDayTime,
  formatJoinDate,
  formatPlan,
  formatTaka,
} from '@/lib/telco-format';
import type { SubscriberDetail } from '@/lib/types/admin';

/** A subscriber's account at a glance, in a side sheet. `id` null keeps it closed. */
export function SubscriberSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  return (
    <Sheet open={id !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="bg-surface w-full gap-0 overflow-y-auto p-0 sm:max-w-[460px]">
        {id && <SheetBody id={id} />}
      </SheetContent>
    </Sheet>
  );
}

function SheetBody({ id }: { id: string }) {
  const { data, error, loading, reload } = useAdminQuery(
    'subscriber',
    () => adminApi.subscriber(id),
    [id]
  );
  // The previous subscriber's data stays in place while a new one loads; never show it as this one.
  const detail = data && data.subscriber.id === id ? data : undefined;

  return (
    <>
      <SheetHeader className="border-line border-b p-5 pr-12">
        {detail ? (
          <div className="flex items-center gap-3">
            <Avatar name={detail.subscriber.full_name} className="size-11 text-xs" />
            <div className="min-w-0">
              <SheetTitle className="truncate text-base font-extrabold">
                {detail.subscriber.full_name}
              </SheetTitle>
              <SheetDescription className="text-[11px]">
                {detail.subscriber.msisdn_masked} · {formatPlan(detail.subscriber.plan_type)} ·{' '}
                {detail.subscriber.district}
              </SheetDescription>
            </div>
          </div>
        ) : (
          <>
            <SheetTitle className="text-base font-extrabold">Subscriber</SheetTitle>
            <SheetDescription className="text-[11px]">
              {error ? 'Could not load this subscriber.' : 'Loading the account…'}
            </SheetDescription>
          </>
        )}
      </SheetHeader>
      <div className="space-y-6 p-5" aria-busy={loading && !detail}>
        {error && !detail ? (
          <LoadError what="This subscriber" error={error} onRetry={reload} />
        ) : detail ? (
          <Detail d={detail} />
        ) : (
          <div className="space-y-3">
            <Bone className="h-16 w-full" />
            <Bone className="h-32 w-full" />
            <Bone className="h-32 w-full" />
          </div>
        )}
      </div>
    </>
  );
}

function Tile({ label, value, foot }: { label: string; value: React.ReactNode; foot?: string }) {
  return (
    <div className="bg-surface2 border-line rounded-xl border p-3">
      <p className="text-muted-foreground text-[11px]">{label}</p>
      <p className="mt-1 text-lg leading-tight font-extrabold tracking-[-0.4px] tabular-nums">
        {value}
      </p>
      {foot && <p className="text-muted-foreground mt-0.5 text-[10px]">{foot}</p>}
    </div>
  );
}

function Section({
  title,
  empty,
  children,
}: {
  title: string;
  empty?: string;
  children?: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-extrabold tracking-[-0.2px]">{title}</h3>
      {empty ? (
        <p className="text-muted-foreground flex items-center gap-2 text-[11px]">
          <InboxIcon className="size-4" aria-hidden="true" />
          {empty}
        </p>
      ) : (
        <ul>{children}</ul>
      )}
    </section>
  );
}

function Detail({ d }: { d: SubscriberDetail }) {
  const { subscriber: s, summary } = d;
  const postpaid = s.plan_type === 'postpaid';
  return (
    <>
      <div className="flex items-center gap-2 text-[11px]">
        <SubscriberStatusChip status={s.status} />
        <span className="text-muted-foreground">Joined {formatJoinDate(s.joined_on)}</span>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <Tile
          label={postpaid ? 'Amount due' : 'Balance'}
          value={postpaid ? formatTaka(s.postpaid_due) : formatTaka(s.main_balance)}
        />
        <Tile label="Reward points" value={s.reward_points.toLocaleString('en-IN')} />
        <Tile
          label="Data left"
          value={formatData(summary.totals.data_left_mb)}
          foot={`${summary.totals.minutes_left} min · ${summary.totals.sms_left} SMS`}
        />
        <Tile label="Open cases" value={summary.open_cases} />
      </div>

      <Section
        title="Recent transactions"
        empty={d.transactions.length === 0 ? 'No transactions yet.' : undefined}
      >
        {d.transactions.map((t) => (
          <li
            key={t.ref}
            className="border-line flex items-center gap-3 border-b py-2.5 text-xs last:border-b-0"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate font-bold">
                {t.package_name ?? (t.type === 'recharge' ? 'Recharge' : t.type)}
              </span>
              <span className="text-muted-foreground block text-[11px]">
                {t.ref} · {formatDayTime(t.created_at)}
              </span>
            </span>
            <span className="font-bold tabular-nums">{formatTaka(t.amount)}</span>
            <TxnStatusChip status={t.status} />
          </li>
        ))}
      </Section>

      <Section title="Cases" empty={d.cases.length === 0 ? 'No cases.' : undefined}>
        {d.cases.map((c) => (
          <li
            key={c.ref}
            className="border-line flex items-center gap-3 border-b py-2.5 text-xs last:border-b-0"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate font-bold">{caseCategoryLabel(c.category)}</span>
              <span className="text-muted-foreground block truncate text-[11px]">
                {c.ref} · {formatDay(c.created_at)}
                {c.priority === 'high' ? ' · High priority' : ''}
              </span>
            </span>
            <CaseStatusChip status={c.status} />
          </li>
        ))}
      </Section>

      <Section
        title="Notifications"
        empty={d.notifications.length === 0 ? 'No notifications sent.' : undefined}
      >
        {d.notifications.map((n) => (
          <li
            key={n.id}
            className="border-line flex items-start gap-3 border-b py-2.5 text-xs last:border-b-0"
          >
            <BellIcon className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block font-bold">{n.title}</span>
              <span className="text-muted-foreground block text-[11px]">{n.body}</span>
              <span className="text-muted-foreground block text-[10px]">
                {formatDayTime(n.created_at)} · {n.read_at ? 'Read' : 'Unread'}
              </span>
            </span>
          </li>
        ))}
      </Section>
    </>
  );
}
