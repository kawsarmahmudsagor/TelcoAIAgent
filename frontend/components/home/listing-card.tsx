import Link from 'next/link';
import { BathIcon, BedDoubleIcon, MapPinIcon, RulerIcon } from 'lucide-react';
import { LISTING_TYPE, PROPERTY_TYPE } from '@/components/dashboard/status-tones';
import { OfferBadge } from '@/components/offers/offer-badge';
import { formatBdt } from '@/lib/format';
import type { PublicListing } from '@/lib/types';
import { PropertyPhoto } from './property-photo';

// One katha is 720 sq ft; land in Dhaka is priced and talked about in katha.
const KATHA_SQFT = 720;
const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 });

/** Beds, baths and floor area (or a plot's size in katha), whichever the listing has. */
export function listingSpecs(
  listing: PublicListing
): { icon: typeof BedDoubleIcon; label: string }[] {
  const out: { icon: typeof BedDoubleIcon; label: string }[] = [];
  if (listing.property_type === 'plot') {
    if (listing.sqft) {
      out.push({ icon: RulerIcon, label: `${number.format(listing.sqft / KATHA_SQFT)} katha` });
    }
    return out;
  }
  if (listing.bedrooms > 0) {
    out.push({
      icon: BedDoubleIcon,
      label: `${listing.bedrooms} ${listing.bedrooms === 1 ? 'bed' : 'beds'}`,
    });
  }
  if (listing.bathrooms > 0) {
    out.push({
      icon: BathIcon,
      label: `${number.format(listing.bathrooms)} ${listing.bathrooms === 1 ? 'bath' : 'baths'}`,
    });
  }
  if (listing.sqft) {
    out.push({ icon: RulerIcon, label: `${number.format(listing.sqft)} sq ft` });
  }
  return out;
}

export function ListingCard({ listing, priority }: { listing: PublicListing; priority?: boolean }) {
  const cover = listing.images?.[0] ?? listing.image_url;
  const area = [listing.neighborhood, listing.city].filter(Boolean).join(', ');
  const typeLabel = PROPERTY_TYPE[listing.property_type] ?? listing.property_type;

  return (
    <Link
      href={`/properties/${listing.id}`}
      className="group bg-card focus-visible:ring-ring/50 hover:border-foreground/20 flex w-full flex-col overflow-hidden rounded-lg border transition-[box-shadow,border-color] duration-200 outline-none hover:shadow-md focus-visible:ring-[3px]"
    >
      <div className="relative aspect-[3/2] overflow-hidden sm:aspect-[4/3]">
        <PropertyPhoto
          src={cover}
          alt={`${listing.title}, ${area}`}
          sizes="(min-width: 1024px) 360px, (min-width: 640px) 50vw, 100vw"
          priority={priority}
          className="transition-transform duration-500 ease-out group-hover:scale-[1.03] motion-reduce:transition-none motion-reduce:group-hover:scale-100"
        />
        <span className="bg-background/90 text-foreground absolute top-3 left-3 rounded-sm px-2 py-1 text-xs font-medium backdrop-blur-sm">
          {LISTING_TYPE[listing.listing_type]}
        </span>
        <OfferBadge
          offers={listing.offers}
          className="absolute top-3 right-3 max-w-[calc(100%-7rem)] shadow-sm"
        />
      </div>
      <div className="flex flex-1 flex-col gap-3 p-5">
        <div>
          <p className="text-muted-foreground flex items-center gap-1.5 text-sm">
            <MapPinIcon aria-hidden="true" className="size-3.5" />
            <span>{area}</span>
            <span aria-hidden="true" className="bg-border mx-1 h-3 w-px" />
            <span>{typeLabel}</span>
          </p>
          <h3 className="font-display mt-1.5 text-lg leading-snug font-semibold text-balance underline-offset-4 group-hover:underline">
            {listing.title}
          </h3>
        </div>
        <ul className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {listingSpecs(listing).map(({ icon: Icon, label }) => (
            <li key={label} className="flex items-center gap-1.5">
              <Icon aria-hidden="true" className="size-4" />
              {label}
            </li>
          ))}
        </ul>
        <p className="mt-auto border-t pt-3">
          <span className="font-display text-xl font-semibold tracking-[-0.01em] tabular-nums">
            {formatBdt(listing.price)}
          </span>
          {listing.listing_type === 'rent' && (
            <span className="text-muted-foreground text-sm"> a month</span>
          )}
        </p>
      </div>
    </Link>
  );
}
