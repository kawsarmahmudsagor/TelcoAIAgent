import Link from 'next/link';
import { ArrowRightIcon, CalendarClockIcon, TagIcon } from 'lucide-react';
import { formatBdt } from '@/lib/format';
import { OFFER_TYPE_LABEL, offerHeadline, offerUntil } from '@/lib/offers';
import { homeFilterHref } from '@/lib/public-listings';
import type { PublicOffer } from '@/lib/types';

const linkClass =
  'focus-visible:ring-ring/50 rounded-sm outline-none underline-offset-4 hover:underline focus-visible:ring-[3px]';

/**
 * One live offer on the home page. Linked offers list their homes (each opens its property page);
 * an all-sale offer links to the featured homes filtered to sale. All links are client-side, so a
 * call in the chat bubble carries on.
 */
export function OfferCard({ offer }: { offer: PublicOffer }) {
  const until = offerUntil(offer);
  return (
    <article className="bg-card flex w-full flex-col gap-4 rounded-lg border p-6">
      <div>
        <p className="text-muted-foreground flex items-center gap-1.5 text-sm">
          <TagIcon aria-hidden="true" className="text-brass size-4" />
          {OFFER_TYPE_LABEL[offer.offer_type]}
        </p>
        <h3 className="font-display mt-2 text-xl leading-snug font-semibold tracking-[-0.01em] text-balance">
          {offer.title}
        </h3>
        <p className="font-display text-primary mt-1 text-lg font-semibold tabular-nums">
          {offerHeadline(offer)}
        </p>
      </div>
      {offer.description && (
        <p className="text-muted-foreground text-sm leading-relaxed">{offer.description}</p>
      )}
      {offer.terms && (
        <p className="text-muted-foreground border-l-2 pl-3 text-xs leading-relaxed">
          {offer.terms}
        </p>
      )}

      <div className="mt-auto flex flex-col gap-3 border-t pt-4 text-sm">
        {until && (
          <p className="text-muted-foreground flex items-center gap-1.5">
            <CalendarClockIcon aria-hidden="true" className="size-4" />
            {until}
          </p>
        )}
        {offer.applies_to_all_sale ? (
          <Link
            href={homeFilterHref({ listing: 'sale' })}
            className={`${linkClass} inline-flex w-fit items-center gap-1.5 font-medium`}
          >
            On every home for sale
            <ArrowRightIcon aria-hidden="true" className="size-4" />
          </Link>
        ) : (
          <ul className="flex flex-col gap-1.5" aria-label={`Homes with ${offer.title}`}>
            {offer.listings.map((l) => (
              <li key={l.id} className="flex items-baseline justify-between gap-3">
                <Link href={`/properties/${l.id}`} className={`${linkClass} min-w-0 font-medium`}>
                  <span className="block truncate">{l.title}</span>
                </Link>
                <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                  {formatBdt(l.price)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
