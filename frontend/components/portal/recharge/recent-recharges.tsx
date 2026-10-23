'use client';

import { ArrowUpRightIcon, ReceiptTextIcon } from 'lucide-react';
import { usePortalMe } from '@/components/portal/portal-me-context';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { formatDayTime, formatTaka } from '@/lib/telco-format';
import type { TxnChannel } from '@/lib/types/portal';

const CHANNEL: Partial<Record<TxnChannel, string>> = {
  bkash: 'bKash',
  nagad: 'Nagad',
  card: 'Card',
};

/** "Recent recharges": the last five, with the number when it went to someone else. */
export function RecentRecharges() {
  const me = usePortalMe();
  const txns = usePortalQuery(
    'transactions',
    () => portalApi.transactions({ type: 'recharge', limit: 5 }),
    { type: 'recharge', limit: 5 }
  );

  return (
    <Panel>
      <PanelHeader
        title={me.plan_type === 'postpaid' ? 'Recent payments' : 'Recent recharges'}
        className="mb-2"
      />
      {txns.data ? (
        txns.data.length === 0 ? (
          <div className="flex items-center gap-3 py-3">
            <ReceiptTextIcon className="text-muted-foreground size-5 shrink-0" aria-hidden="true" />
            <p className="text-muted-foreground text-[11px]">
              Nothing yet. Your {me.plan_type === 'postpaid' ? 'payments' : 'recharges'} will show
              up here.
            </p>
          </div>
        ) : (
          <ul>
            {txns.data.map((txn) => {
              const other = txn.target_msisdn && txn.target_msisdn !== me.msisdn;
              return (
                <li
                  key={txn.ref}
                  className="border-line flex items-center gap-[11px] border-b py-[13px] last:border-b-0 last:pb-0"
                >
                  <span
                    aria-hidden="true"
                    className="bg-surface2 grid size-9 shrink-0 place-items-center rounded-[11px] [&_svg]:size-4"
                  >
                    <ArrowUpRightIcon />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[11px] font-bold">
                      {formatTaka(txn.amount)} · {CHANNEL[txn.channel] ?? txn.channel}
                    </p>
                    <p className="text-muted-foreground truncate text-[10px]">
                      {formatDayTime(txn.created_at)}
                      {other && ` · to ${txn.target_msisdn}`}
                    </p>
                    {txn.failure_reason && (
                      <p className="text-status-failed-foreground truncate text-[10px]">
                        {txn.failure_reason}
                      </p>
                    )}
                  </div>
                  <StatusChip tone={txn.status}>{txn.status}</StatusChip>
                </li>
              );
            })}
          </ul>
        )
      ) : txns.error && !txns.loading ? (
        <LoadError what="Your recharges" error={txns.error} onRetry={txns.reload} />
      ) : (
        <ul aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <li key={i} className="flex items-center gap-[11px] py-[13px]">
              <Bone className="size-9 rounded-[11px]" />
              <div className="flex-1 space-y-2">
                <Bone className="h-3 w-1/2" />
                <Bone className="h-2.5 w-1/3" />
              </div>
              <Bone className="h-4 w-14" />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
