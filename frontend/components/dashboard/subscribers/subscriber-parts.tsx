import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import { formatTaka } from '@/lib/telco-format';
import type { SubscriberItem, SubscriberStatus } from '@/lib/types/admin';
import type { TxnStatus } from '@/lib/types/portal';

const STATUS: Record<SubscriberStatus, { tone: StatusTone; label: string }> = {
  active: { tone: 'success', label: 'Active' },
  suspended: { tone: 'failed', label: 'Suspended' },
};

export function SubscriberStatusChip({ status }: { status: SubscriberStatus | string }) {
  const s = STATUS[status as SubscriberStatus] ?? { tone: 'open' as const, label: status };
  return <StatusChip tone={s.tone}>{s.label}</StatusChip>;
}

const TXN: Record<TxnStatus, { tone: StatusTone; label: string }> = {
  success: { tone: 'success', label: 'Success' },
  pending: { tone: 'pending', label: 'Pending' },
  failed: { tone: 'failed', label: 'Failed' },
};

export function TxnStatusChip({ status }: { status: TxnStatus | string }) {
  const s = TXN[status as TxnStatus] ?? { tone: 'open' as const, label: status };
  return <StatusChip tone={s.tone}>{s.label}</StatusChip>;
}

/** Prepaid shows the balance; postpaid shows what is owed. */
export function balanceText(
  s: Pick<SubscriberItem, 'plan_type' | 'main_balance' | 'postpaid_due'>
) {
  return s.plan_type === 'postpaid'
    ? `${formatTaka(s.postpaid_due)} due`
    : formatTaka(s.main_balance);
}
