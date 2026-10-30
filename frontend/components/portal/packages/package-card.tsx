'use client';

import { forwardRef } from 'react';
import { MessageSquareTextIcon, PhoneIcon, SparklesIcon, WifiIcon } from 'lucide-react';
import { PortalButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';
import { formatData, formatTaka } from '@/lib/telco-format';
import type { PackageView } from '@/lib/types/portal';

const KIND_TAG = { data: 'Data', voice: 'Voice', bundle: 'Bundle', sms: 'SMS' } as const;
const DECO = { data: WifiIcon, bundle: WifiIcon, voice: PhoneIcon, sms: MessageSquareTextIcon };

/** What the pack holds: "8.0 GB anytime internet", "15.0 GB internet + 300 minutes". */
export function packageContents(pkg: PackageView): string {
  if (pkg.kind === 'voice') return `${pkg.minutes} minutes to any local operator`;
  if (pkg.kind === 'sms') return `${pkg.sms} local SMS`;
  if (pkg.kind === 'data') return `${formatData(pkg.data_mb)} anytime internet`;
  const parts = [`${formatData(pkg.data_mb)} internet`];
  if (pkg.minutes > 0) parts.push(`${pkg.minutes} minutes`);
  if (pkg.sms > 0) parts.push(`${pkg.sms} SMS`);
  return parts.join(' + ');
}

export function validity(days: number): string {
  return days === 1 ? '1 day' : `${days} days`;
}

/** Whether the pack renews itself: "Auto-renews" or "No auto-renew". */
export function renewal(pkg: PackageView): string {
  return pkg.auto_renewable ? 'Auto-renews' : 'No auto-renew';
}

/**
 * One pack in the reference's offer-card style: tag, name, contents, validity, price, "Buy pack".
 * The POPULAR pack gets the featured lilac card; `highlighted` rings the card a link pointed at.
 */
export const PackageCard = forwardRef<
  HTMLLIElement,
  { pkg: PackageView; highlighted: boolean; onBuy(): void }
>(function PackageCard({ pkg, highlighted, onBuy }, ref) {
  const featured = pkg.tag?.toUpperCase() === 'POPULAR';
  const Deco = DECO[pkg.kind];
  const muted = featured ? 'text-featured-muted' : 'text-muted-foreground';

  return (
    <li
      ref={ref}
      id={`pack-${pkg.code}`}
      className={cn(
        'rounded-metric phone:p-[17px] relative flex min-w-0 scroll-mt-24 flex-col overflow-hidden border p-[18px]',
        featured
          ? 'border-featured-border from-featured-from to-featured-to text-featured-fg bg-linear-145'
          : 'bg-surface border-line',
        highlighted && 'ring-brand ring-offset-background ring-2 ring-offset-2'
      )}
    >
      <span
        className={cn(
          'inline-flex items-center gap-1 self-start rounded-md px-[7px] py-[5px] text-[9px] font-extrabold tracking-[0.7px] uppercase',
          featured ? 'bg-featured-chip text-featured-chip-fg' : 'bg-tint-purple text-brand-text'
        )}
      >
        {featured && <SparklesIcon className="size-2.5" aria-hidden="true" />}
        {pkg.tag ?? KIND_TAG[pkg.kind]}
      </span>
      <Deco
        aria-hidden="true"
        className="absolute top-[42px] -right-2.5 size-[58px] opacity-[0.09]"
      />
      <h3 className="mt-3.5 mb-1 text-[22px] leading-tight font-black tracking-[-0.8px]">
        {pkg.name}
      </h3>
      <p className={cn('text-[11px]', muted)}>{packageContents(pkg)}</p>
      <p className={cn('text-[11px]', muted)}>Valid for {validity(pkg.validity_days)}</p>
      <p className={cn('text-[11px]', muted)}>{renewal(pkg)}</p>
      <div className="mt-auto flex items-center justify-between gap-2 pt-[17px]">
        <p className="text-sm font-extrabold">{formatTaka(pkg.price)}</p>
        <PortalButton
          variant={featured || highlighted ? 'primary' : 'soft'}
          onClick={onBuy}
          aria-label={`Buy pack: ${pkg.name}`}
        >
          Buy pack
        </PortalButton>
      </div>
    </li>
  );
});
