import { TagIcon } from 'lucide-react';
import { offerHeadline } from '@/lib/offers';
import { cn } from '@/lib/shadcn/utils';
import type { ListingOffer } from '@/lib/types';

/**
 * The listing's first live offer in a few words, plus "+n" when it has more. Renders nothing
 * without offers. Server- and client-safe (no hooks).
 */
export function OfferBadge({
  offers,
  size = 'md',
  className,
}: {
  offers: ListingOffer[] | undefined;
  size?: 'sm' | 'md';
  className?: string;
}) {
  if (!offers?.length) return null;
  const [first, ...rest] = offers;
  const label = offers.map((o) => o.title).join(' · ');
  return (
    <span
      title={label}
      className={cn(
        'bg-brass text-brass-foreground inline-flex max-w-full items-center gap-1 rounded-full font-semibold',
        size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
        className
      )}
    >
      <TagIcon aria-hidden="true" className={size === 'sm' ? 'size-3' : 'size-3.5'} />
      <span className="sr-only">Offer: </span>
      <span className="truncate">{offerHeadline(first)}</span>
      {rest.length > 0 && (
        <span className="shrink-0 opacity-80">
          +{rest.length}
          <span className="sr-only"> more {rest.length === 1 ? 'offer' : 'offers'}</span>
        </span>
      )}
    </span>
  );
}
