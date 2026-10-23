'use client';

import { ArrowUpRightIcon, GiftIcon, Loader2Icon, PercentIcon, SparklesIcon } from 'lucide-react';
import { packageContents, validity } from '@/components/portal/packages/package-card';
import { LinkButton, PortalButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';
import { formatData, formatDay, formatTaka } from '@/lib/telco-format';
import type { OfferView, PackageView } from '@/lib/types/portal';

/** Which action an offer gets, from the fields the backend fills. */
export type OfferVariant = 'points' | 'cashback' | 'package' | 'info';

export function offerVariant(offer: OfferView): OfferVariant {
  if (offer.points_cost !== null) return 'points';
  if (offer.cashback_percent !== null) return 'cashback';
  if (offer.package !== null) return 'package';
  return 'info';
}

/** The pack's headline allowance ("20 GB", "300 min", "100 SMS"). */
function allowance(pkg: PackageView): string {
  if (pkg.data_mb > 0) return formatData(pkg.data_mb);
  if (pkg.minutes > 0) return `${pkg.minutes} min`;
  return `${pkg.sms} SMS`;
}

const TAG: Record<OfferVariant, string> = {
  points: 'Reward redemption',
  cashback: 'Cashback',
  package: 'Exclusive',
  info: 'Offer',
};

const pts = (n: number) => n.toLocaleString('en-IN');

/**
 * One offer in the reference's offer-card style. Points offers redeem (disabled while short of
 * points), cashback offers go to Recharge, pack offers to that pack in My packages.
 */
export function OfferCard({
  offer,
  points,
  redeeming,
  onRedeem,
}: {
  offer: OfferView;
  points: number;
  /** A redemption of this offer is starting. */
  redeeming: boolean;
  onRedeem(): void;
}) {
  const variant = offerVariant(offer);
  const featured = variant === 'package';
  const muted = featured ? 'text-featured-muted' : 'text-muted-foreground';
  const pkg = offer.package;

  let headline = offer.title;
  let meta = offer.description ?? '';
  let price: React.ReactNode = null;
  let action: React.ReactNode = null;

  if (variant === 'points' && offer.points_cost !== null) {
    const short = offer.points_cost - points;
    headline = pkg ? `${allowance(pkg)} free` : offer.title;
    meta = `Redeem with ${pts(offer.points_cost)} points${pkg ? ` · ${validity(pkg.validity_days)}` : ''}`;
    price = (
      <>
        {pts(offer.points_cost)} <small className={cn('text-[10px] font-medium', muted)}>pts</small>
      </>
    );
    action = (
      <PortalButton
        variant="soft"
        onClick={onRedeem}
        disabled={short > 0 || redeeming}
        aria-label={short > 0 ? undefined : `Redeem: ${offer.title}`}
      >
        {redeeming && <Loader2Icon className="animate-spin" aria-hidden="true" />}
        {short > 0 ? `Need ${pts(short)} more points` : 'Redeem'}
      </PortalButton>
    );
  } else if (variant === 'cashback' && offer.cashback_percent !== null) {
    headline = `${offer.cashback_percent}% back`;
    meta =
      offer.min_recharge !== null
        ? `On a recharge of ${formatTaka(offer.min_recharge)} or more`
        : 'On any recharge';
    price = offer.cashback_cap !== null ? `Up to ${formatTaka(offer.cashback_cap)}` : null;
    action = (
      <LinkButton href="/portal/recharge" variant="soft">
        Recharge
        <ArrowUpRightIcon aria-hidden="true" />
      </LinkButton>
    );
  } else if (variant === 'package' && pkg) {
    headline = allowance(pkg);
    meta = `${packageContents(pkg)} · ${validity(pkg.validity_days)}`;
    price = formatTaka(pkg.price);
    action = (
      <LinkButton
        href={`/portal/packages?highlight=${encodeURIComponent(pkg.code)}`}
        aria-label={`Get pack: ${pkg.name}`}
      >
        Get pack
        <ArrowUpRightIcon aria-hidden="true" />
      </LinkButton>
    );
  }

  const Deco =
    variant === 'cashback' ? PercentIcon : variant === 'points' ? GiftIcon : SparklesIcon;

  return (
    <li
      className={cn(
        'rounded-metric phone:p-[17px] relative flex min-w-0 flex-col overflow-hidden border p-[18px]',
        featured
          ? 'border-featured-border from-featured-from to-featured-to text-featured-fg bg-linear-145'
          : 'bg-surface border-line'
      )}
    >
      <span
        className={cn(
          'inline-flex items-center gap-1 self-start rounded-md px-[7px] py-[5px] text-[9px] font-extrabold tracking-[0.7px] uppercase',
          featured ? 'bg-featured-chip text-featured-chip-fg' : 'bg-tint-purple text-brand-text'
        )}
      >
        {featured && <SparklesIcon className="size-2.5" aria-hidden="true" />}
        {TAG[variant]}
      </span>
      <Deco
        aria-hidden="true"
        className="absolute top-[42px] -right-2.5 size-[58px] opacity-[0.09]"
      />
      <h3 className="mt-3.5 mb-0.5 text-[27px] leading-tight font-black tracking-[-1px]">
        {headline}
      </h3>
      <p className={cn('text-[11px]', muted)}>{meta}</p>
      {offer.ends_on && (
        <p className={cn('mt-1 text-[10px]', muted)}>Ends {formatDay(offer.ends_on)}</p>
      )}
      {(price || action) && (
        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-[17px]">
          <p className="text-sm font-extrabold">{price}</p>
          {action}
        </div>
      )}
    </li>
  );
}
