import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import { formatDay, formatTaka } from '@/lib/telco-format';
import type { AdminOffer, OfferAudience, OfferKind } from '@/lib/types/admin';

export const KIND_LABEL: Record<OfferKind, string> = {
  pack: 'Pack',
  points: 'Points',
  cashback: 'Cashback',
};

export const KINDS: OfferKind[] = ['pack', 'points', 'cashback'];

export const AUDIENCE_LABEL: Record<OfferAudience, string> = {
  all: 'Everyone',
  prepaid: 'Prepaid',
  postpaid: 'Postpaid',
  specific: 'Chosen subscribers',
};

const KIND_TONE: Record<OfferKind, StatusTone> = {
  pack: 'open',
  points: 'pending',
  cashback: 'success',
};

export function KindChip({ kind }: { kind: OfferKind }) {
  return <StatusChip tone={KIND_TONE[kind] ?? 'open'}>{KIND_LABEL[kind] ?? kind}</StatusChip>;
}

export function AudienceChip({ offer }: { offer: AdminOffer }) {
  const text =
    offer.audience === 'specific'
      ? `${offer.subscriber_ids.length} chosen`
      : (AUDIENCE_LABEL[offer.audience] ?? offer.audience);
  return (
    <span
      className="bg-tint-purple text-brand dark:text-brand2 inline-block rounded-md px-[7px] py-1 text-[10px] leading-none font-extrabold whitespace-nowrap"
      title={
        offer.audience === 'specific'
          ? offer.subscribers.map((s) => `${s.full_name} ${s.msisdn_masked}`).join(', ')
          : undefined
      }
    >
      {text}
    </span>
  );
}

/** What the offer gives, in one line. */
export function valueText(o: AdminOffer): string {
  if (o.kind === 'points') {
    return `${(o.points_cost ?? 0).toLocaleString('en-IN')} points for ${o.package_name ?? 'a package'}`;
  }
  if (o.kind === 'cashback') {
    const cap = o.cashback_cap !== null ? `, up to ${formatTaka(o.cashback_cap)}` : '';
    return `${o.cashback_percent}% back on recharges from ${formatTaka(o.min_recharge ?? 0)}${cap}`;
  }
  return o.package_name ?? 'A package';
}

/** "1 Nov to 30 Nov", "From 1 Nov", "Until 30 Nov" or "Always on". */
export function validityText(o: Pick<AdminOffer, 'starts_on' | 'ends_on'>): string {
  if (o.starts_on && o.ends_on) return `${formatDay(o.starts_on)} to ${formatDay(o.ends_on)}`;
  if (o.starts_on) return `From ${formatDay(o.starts_on)}`;
  if (o.ends_on) return `Until ${formatDay(o.ends_on)}`;
  return 'Always on';
}
