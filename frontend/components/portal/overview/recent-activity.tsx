'use client';

import { ArrowUpRightIcon, GiftIcon, PackageIcon, ReceiptTextIcon } from 'lucide-react';
import { usePortalMe } from '@/components/portal/portal-me-context';
import { LinkButton, SmallLink } from '@/components/portal/ui/link-button';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { cn } from '@/lib/shadcn/utils';
import { formatDayTime, formatTaka } from '@/lib/telco-format';
import type { TransactionView, TxnChannel, TxnType } from '@/lib/types/portal';

const CHANNEL: Record<TxnChannel, string> = {
  bkash: 'bKash',
  nagad: 'Nagad',
  card: 'Card',
  balance: 'Main balance',
  points: 'Reward points',
};

const ICON: Record<TxnType, typeof GiftIcon> = {
  recharge: ArrowUpRightIcon,
  purchase: PackageIcon,
  redeem: GiftIcon,
};

function title(txn: TransactionView, ownMsisdn: string): string {
  if (txn.type === 'recharge') {
    return txn.target_msisdn && txn.target_msisdn !== ownMsisdn
      ? `Recharge to ${txn.target_msisdn}`
      : 'Mobile recharge';
  }
  if (txn.type === 'purchase') return txn.package_name ?? 'Pack purchase';
  return txn.package_name ? `${txn.package_name} reward` : 'Reward redeemed';
}

/**
 * Recharges add (+), purchases spend (−). A points redemption carries no taka amount, so it
 * shows the points spent.
 */
function amount(txn: TransactionView): string {
  if (txn.type === 'recharge') return `+${formatTaka(txn.amount)}`;
  if (txn.channel === 'points') {
    return txn.points_spent !== null ? `${txn.points_spent.toLocaleString('en-IN')} pts` : 'Points';
  }
  return `−${formatTaka(txn.amount)}`;
}

/** "Recent activity": the customer's last five transactions. */
export function RecentActivity() {
  const me = usePortalMe();
  const txns = usePortalQuery('transactions', () => portalApi.transactions({ limit: 5 }));

  return (
    <Panel>
      <PanelHeader
        title="Recent activity"
        description="Your latest transactions"
        action={
          <SmallLink href="/portal/recharge">
            View all
            <ArrowUpRightIcon aria-hidden="true" />
          </SmallLink>
        }
      />
      {txns.data ? (
        txns.data.length === 0 ? (
          <div className="flex flex-col items-start gap-3 py-2">
            <ReceiptTextIcon className="text-muted-foreground size-6" aria-hidden="true" />
            <div>
              <p className="text-sm font-bold">No transactions yet</p>
              <p className="text-muted-foreground mt-1 text-[11px]">
                Recharges, pack purchases and rewards will show up here.
              </p>
            </div>
            <LinkButton href="/portal/recharge" variant="soft">
              Recharge now
            </LinkButton>
          </div>
        ) : (
          <ul>
            {txns.data.slice(0, 5).map((txn) => {
              const Icon = ICON[txn.type];
              return (
                <li
                  key={txn.ref}
                  className="border-line flex items-center gap-[11px] border-b py-[13px] last:border-b-0 last:pb-0"
                >
                  <span
                    aria-hidden="true"
                    className="bg-surface2 grid size-9 shrink-0 place-items-center rounded-[11px] [&_svg]:size-4"
                  >
                    <Icon />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[11px] font-bold">{title(txn, me.msisdn)}</p>
                    <p className="text-muted-foreground truncate text-[10px]">
                      {formatDayTime(txn.created_at)} · {CHANNEL[txn.channel]}
                    </p>
                    {txn.failure_reason && (
                      <p className="text-status-failed-foreground truncate text-[10px]">
                        {txn.failure_reason}
                      </p>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <p
                      className={cn(
                        'mb-1 text-xs font-extrabold whitespace-nowrap',
                        txn.status === 'failed' && 'text-muted-foreground line-through'
                      )}
                    >
                      {amount(txn)}
                    </p>
                    <StatusChip tone={txn.status}>{txn.status}</StatusChip>
                  </div>
                </li>
              );
            })}
          </ul>
        )
      ) : txns.error && !txns.loading ? (
        <LoadError what="Your transactions" error={txns.error} onRetry={txns.reload} />
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
