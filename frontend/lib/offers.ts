import { formatBdt, formatShortDay } from '@/lib/format';
import type { OfferType } from '@/lib/types';

/** The fields every offer shape has (dashboard, public list and listing badge). */
interface OfferLike {
  offer_type: OfferType;
  discount_percent: number | null;
  discount_amount: number | null;
  ends_on: string | null;
}

export const OFFER_TYPE_LABEL: Record<OfferType, string> = {
  percent_discount: 'Percent discount',
  flat_discount: 'Flat discount',
  single_payment_discount: 'Single-payment discount',
  installment_plan: 'Installment plan',
  reduced_booking_money: 'Reduced booking money',
  fee_waiver: 'Fee waiver',
  free_parking: 'Free parking',
};

/** Types whose percentage is required, and the one whose taka amount is. */
export const PERCENT_TYPES: readonly OfferType[] = ['percent_discount', 'single_payment_discount'];
export const AMOUNT_REQUIRED_TYPES: readonly OfferType[] = ['flat_discount'];
/** Perks where a taka amount is optional context (the booking money, the fee waived). */
export const AMOUNT_OPTIONAL_TYPES: readonly OfferType[] = ['reduced_booking_money', 'fee_waiver'];

const percent = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

/** The offer in a few words, for a badge: "8% off", "৳10,00,000 off", "Free parking". */
export function offerHeadline(offer: OfferLike): string {
  const pct = offer.discount_percent;
  const amount = offer.discount_amount;
  switch (offer.offer_type) {
    case 'percent_discount':
      return pct !== null ? `${percent.format(pct)}% off` : 'Discount';
    case 'single_payment_discount':
      return pct !== null ? `${percent.format(pct)}% off, paid in full` : 'Pay-in-full discount';
    case 'flat_discount':
      return amount !== null ? `${formatBdt(amount)} off` : 'Flat discount';
    case 'reduced_booking_money':
      return amount !== null ? `Book with ${formatBdt(amount)}` : 'Lower booking money';
    case 'fee_waiver':
      return amount !== null ? `${formatBdt(amount)} fees waived` : 'Fees waived';
    case 'installment_plan':
      return 'Installment plan';
    case 'free_parking':
      return 'Free parking';
  }
}

/** "Until 12 Dec", or null for an open-ended offer. */
export function offerUntil(offer: OfferLike): string | null {
  return offer.ends_on ? `Until ${formatShortDay(offer.ends_on)}` : null;
}
