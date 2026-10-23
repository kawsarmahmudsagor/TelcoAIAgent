import { PersonCell } from '@/components/dashboard/person-cell';
import { TxnStatusChip } from '@/components/dashboard/subscribers/subscriber-parts';
import { cn } from '@/lib/shadcn/utils';
import { formatDayTime, formatTaka } from '@/lib/telco-format';
import type { AdminTransaction } from '@/lib/types/admin';
import type { TxnChannel, TxnType } from '@/lib/types/portal';

const CHANNEL: Record<TxnChannel, string> = {
  bkash: 'bKash',
  nagad: 'Nagad',
  card: 'Card',
  balance: 'Main balance',
  points: 'Reward points',
};

const TYPE: Record<TxnType, string> = {
  recharge: 'Recharge',
  purchase: 'Package',
  redeem: 'Redeem',
};

function typeText(t: AdminTransaction): string {
  const base = TYPE[t.type] ?? t.type;
  return t.package_name && t.type !== 'recharge' ? `${base}: ${t.package_name}` : base;
}

function Person({ t }: { t: AdminTransaction }) {
  return <PersonCell name={t.subscriber_name} msisdn={t.msisdn_masked} />;
}

/** Why a payment failed, in words (not only in a tooltip, so touch screens see it too). */
function Reason({ t, className }: { t: AdminTransaction; className?: string }) {
  if (t.status !== 'failed') return null;
  return (
    <p
      className={cn('text-destructive text-[11px]', className)}
      title={t.failure_reason ?? undefined}
    >
      {t.failure_reason ?? 'No reason recorded'}
    </p>
  );
}

/** A table, or stacked cards at 1100px and below. */
export function TxnTable({ items }: { items: AdminTransaction[] }) {
  return (
    <>
      <table className="tablet:hidden w-full border-collapse text-left">
        <caption className="sr-only">Transactions, newest first</caption>
        <thead>
          <tr className="text-muted-foreground border-line border-b text-[11px]">
            {['Reference', 'Subscriber', 'Type', 'Channel', 'Amount', 'Time', 'Status'].map((h) => (
              <th key={h} scope="col" className="py-2.5 pr-3 font-semibold whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.ref} className="border-line border-b align-top text-xs last:border-b-0">
              <th scope="row" className="py-3 pr-3 text-left font-bold whitespace-nowrap">
                {t.ref}
              </th>
              <td className="max-w-[220px] py-3 pr-3">
                <Person t={t} />
              </td>
              <td className="max-w-[180px] truncate py-3 pr-3">{typeText(t)}</td>
              <td className="py-3 pr-3 whitespace-nowrap">{CHANNEL[t.channel] ?? t.channel}</td>
              <td className="py-3 pr-3 whitespace-nowrap tabular-nums">{formatTaka(t.amount)}</td>
              <td className="py-3 pr-3 whitespace-nowrap">{formatDayTime(t.created_at)}</td>
              <td className="max-w-[200px] py-3">
                <TxnStatusChip status={t.status} />
                <Reason t={t} className="mt-1 truncate" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="tablet:block hidden">
        {items.map((t) => (
          <li
            key={t.ref}
            className="border-line border-b py-3.5 first:pt-0 last:border-b-0 last:pb-0"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <Person t={t} />
              <TxnStatusChip status={t.status} />
            </div>
            <div className="flex items-center justify-between gap-2 text-xs">
              <p className="font-bold">{t.ref}</p>
              <p className="font-bold tabular-nums">{formatTaka(t.amount)}</p>
            </div>
            <p className="text-muted-foreground mt-0.5 text-[11px]">
              {typeText(t)} · {CHANNEL[t.channel] ?? t.channel} · {formatDayTime(t.created_at)}
            </p>
            <Reason t={t} className="mt-1" />
          </li>
        ))}
      </ul>
    </>
  );
}
