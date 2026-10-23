import type { PackageView, SubscriptionView } from '@/lib/types/portal';

export type AllowanceKind = 'data' | 'minutes' | 'sms';

/** One allowance (data MB, minutes or SMS) summed over the customer's active packs. */
export interface AllowanceLine {
  left: number;
  /** What the packs included; null when a pack holding it isn't in the catalogue (or it hasn't loaded). */
  total: number | null;
  /** The earliest expiry among the packs holding it; null when no pack holds it. */
  expiresAt: string | null;
}

const LEFT = { data: 'data_left_mb', minutes: 'minutes_left', sms: 'sms_left' } as const;
const INCLUDED = { data: 'data_mb', minutes: 'minutes', sms: 'sms' } as const;

/**
 * Left vs included for each allowance. Subscriptions only carry what is left, so each one's
 * `package_code` is joined against the package catalogue for the included amount.
 */
export function allowanceLines(
  subscriptions: SubscriptionView[],
  packages: PackageView[] | undefined
): Record<AllowanceKind, AllowanceLine> {
  const byCode = new Map(packages?.map((p) => [p.code, p]));
  const line = (kind: AllowanceKind): AllowanceLine => {
    let left = 0;
    let total: number | null = packages ? 0 : null;
    let expiresAt: string | null = null;
    for (const sub of subscriptions) {
      const pkg = byCode.get(sub.package_code);
      const holds = pkg ? pkg[INCLUDED[kind]] > 0 : sub[LEFT[kind]] > 0;
      if (!holds) continue;
      left += sub[LEFT[kind]];
      total = pkg && total !== null ? total + pkg[INCLUDED[kind]] : null;
      if (expiresAt === null || Date.parse(sub.expires_at) < Date.parse(expiresAt)) {
        expiresAt = sub.expires_at;
      }
    }
    return { left, total, expiresAt };
  };
  return { data: line('data'), minutes: line('minutes'), sms: line('sms') };
}

/** The subscription that expires first, or null with no active pack. */
export function nearestExpiring(subscriptions: SubscriptionView[]): SubscriptionView | null {
  return subscriptions.reduce<SubscriptionView | null>(
    (soonest, sub) =>
      soonest === null || Date.parse(sub.expires_at) < Date.parse(soonest.expires_at)
        ? sub
        : soonest,
    null
  );
}
