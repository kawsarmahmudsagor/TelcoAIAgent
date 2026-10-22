import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowLeftIcon,
  CalendarDaysIcon,
  CheckIcon,
  MapPinIcon,
  PhoneIcon,
  TagIcon,
} from 'lucide-react';
import { OpenChatButton } from '@/components/chat-bubble/open-chat-button';
import { LISTING_TYPE, PROPERTY_TYPE } from '@/components/dashboard/status-tones';
import { listingSpecs } from '@/components/home/listing-card';
import { SiteFooter } from '@/components/home/site-footer';
import { SiteNav } from '@/components/home/site-nav';
import { PropertyGallery } from '@/components/property/property-gallery';
import { ViewingProperty } from '@/components/property/viewing-property';
import { formatBdt } from '@/lib/format';
import { OFFER_TYPE_LABEL, offerHeadline, offerUntil } from '@/lib/offers';
import { getAgentInfo, getListing, getLiveOffers } from '@/lib/public-listings';
import type { ListingOffer, PublicListing, PublicOffer } from '@/lib/types';

const PLACEHOLDER = '/listings/placeholder.jpg';

const availableDate = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

/** A calendar day ("2026-10-09") as "9 October 2026", without shifting it through UTC. */
function formatAvailable(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  return availableDate.format(new Date(y, m - 1, d));
}

function formatAmenity(amenity: string): string {
  const words = amenity.split('_').join(' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function areaOf(listing: PublicListing): string {
  return [listing.neighborhood, listing.city].filter(Boolean).join(', ');
}

function photosOf(listing: PublicListing): string[] {
  if (listing.images?.length) return listing.images;
  return [listing.image_url || PLACEHOLDER];
}

/** The listing, or a 404 inside the (site) layout, so a live call in the bubble stays up. */
async function loadListing(id: string): Promise<PublicListing> {
  const listing = await getListing(id);
  if (listing === 'not-found') notFound();
  // Rendered by (site)/error.tsx, again without leaving the layout.
  if (listing === null) throw new Error('The listings service is unavailable');
  return listing;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const listing = await getListing((await params).id);
  if (listing === 'not-found' || listing === null) return { title: 'Property' };
  const description =
    listing.description?.slice(0, 160) ??
    `${PROPERTY_TYPE[listing.property_type]} ${LISTING_TYPE[listing.listing_type].toLowerCase()} in ${areaOf(listing)}.`;
  return {
    title: { absolute: `${listing.title}, ${areaOf(listing)} | Horizon Realty` },
    description,
    openGraph: {
      type: 'website',
      siteName: 'Horizon Realty',
      title: listing.title,
      description,
      locale: 'en_BD',
      images: photosOf(listing).slice(0, 1),
    },
  };
}

export default async function PropertyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [listing, agentInfo, liveOffers] = await Promise.all([
    loadListing(id),
    getAgentInfo(),
    getLiveOffers(),
  ]);
  const area = areaOf(listing);
  const typeLabel = PROPERTY_TYPE[listing.property_type] ?? listing.property_type;
  const askLabel = agentInfo
    ? `Ask ${agentInfo.assistant_name} about this home`
    : 'Ask our assistant';
  const specs = listingSpecs(listing);

  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#main"
        className="bg-primary text-primary-foreground sr-only z-50 rounded-md px-4 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <SiteNav />
      <ViewingProperty id={listing.id} />
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 pb-20 sm:px-8 sm:pt-8">
        <Link
          href="/home#homes"
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 -m-1 inline-flex items-center gap-1.5 rounded-md p-1 text-sm outline-none focus-visible:ring-[3px]"
        >
          <ArrowLeftIcon aria-hidden="true" className="size-4" />
          Featured homes
        </Link>

        <div className="mt-4 grid gap-10 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <PropertyGallery photos={photosOf(listing)} alt={`${listing.title}, ${area}`} />
          </div>

          <aside className="flex flex-col gap-6 lg:sticky lg:top-24 lg:self-start">
            <div>
              <p className="text-muted-foreground flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm">
                <span className="bg-muted text-foreground rounded-sm px-2 py-0.5 text-xs font-medium">
                  {LISTING_TYPE[listing.listing_type]}
                </span>
                <span>{typeLabel}</span>
              </p>
              <h1 className="font-display mt-3 text-3xl leading-tight font-semibold tracking-[-0.02em] text-balance sm:text-4xl">
                {listing.title}
              </h1>
              <p className="text-muted-foreground mt-2 flex items-center gap-1.5">
                <MapPinIcon aria-hidden="true" className="size-4 shrink-0" />
                {area}
              </p>
            </div>

            <p>
              <span className="font-display text-3xl font-semibold tracking-[-0.01em] tabular-nums">
                {formatBdt(listing.price)}
              </span>
              {listing.listing_type === 'rent' && (
                <span className="text-muted-foreground"> a month</span>
              )}
            </p>

            <ListingOffers offers={listing.offers} details={liveOffers} />

            {specs.length > 0 && (
              <ul className="flex flex-wrap gap-x-5 gap-y-2 border-y py-4">
                {specs.map(({ icon: Icon, label }) => (
                  <li key={label} className="flex items-center gap-2">
                    <Icon aria-hidden="true" className="text-muted-foreground size-5" />
                    {label}
                  </li>
                ))}
              </ul>
            )}

            {listing.available_from && (
              <p className="text-muted-foreground flex items-center gap-2 text-sm">
                <CalendarDaysIcon aria-hidden="true" className="size-4" />
                Available from {formatAvailable(listing.available_from)}
              </p>
            )}

            <div className="bg-muted/50 rounded-lg border p-5">
              <p className="font-medium">Questions, or want to see it in person?</p>
              <p className="text-muted-foreground mt-1 text-sm">
                Our AI agent knows this listing and can book a viewing with our team, by chat or by
                voice.
              </p>
              <OpenChatButton size="lg" className="mt-4 w-full">
                <PhoneIcon aria-hidden="true" />
                {askLabel}
              </OpenChatButton>
            </div>
          </aside>
        </div>

        <div className="mt-12 grid gap-12 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-12">
            {listing.description && (
              <section aria-labelledby="about-title">
                <h2 id="about-title" className="font-display text-2xl font-semibold">
                  About this home
                </h2>
                <p className="text-muted-foreground mt-3 max-w-prose leading-relaxed whitespace-pre-line">
                  {listing.description}
                </p>
              </section>
            )}

            {listing.amenities.length > 0 && (
              <section aria-labelledby="amenities-title">
                <h2 id="amenities-title" className="font-display text-2xl font-semibold">
                  Amenities
                </h2>
                <ul className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                  {listing.amenities.map((amenity) => (
                    <li key={amenity} className="flex items-center gap-2">
                      <CheckIcon aria-hidden="true" className="text-primary size-4 shrink-0" />
                      {formatAmenity(amenity)}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          <section aria-labelledby="location-title">
            <h2 id="location-title" className="font-display text-2xl font-semibold">
              Location
            </h2>
            <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
              {listing.neighborhood && (
                <>
                  <dt className="text-muted-foreground">Area</dt>
                  <dd>{listing.neighborhood}</dd>
                </>
              )}
              <dt className="text-muted-foreground">City</dt>
              <dd>{listing.city}</dd>
            </dl>
            <p className="text-muted-foreground mt-3 text-sm">
              We share the exact address when your viewing is booked.
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

/**
 * The listing's live offers. Terms and descriptions come from the public offers list when it
 * loaded; the badge fields on the listing are enough on their own.
 */
function ListingOffers({
  offers,
  details,
}: {
  offers: ListingOffer[] | undefined;
  details: PublicOffer[] | null;
}) {
  if (!offers?.length) return null;
  const byId = new Map(details?.map((o) => [o.id, o]));
  return (
    <section aria-labelledby="offers-title" className="rounded-lg border p-5">
      <h2 id="offers-title" className="flex items-center gap-2 font-semibold">
        <TagIcon aria-hidden="true" className="text-brass size-4" />
        {offers.length === 1 ? 'Offer on this home' : 'Offers on this home'}
      </h2>
      <ul className="mt-3 flex flex-col gap-4">
        {offers.map((offer) => {
          const detail = byId.get(offer.id);
          const until = offerUntil(offer);
          return (
            <li key={offer.id}>
              <p className="text-primary font-semibold tabular-nums">{offerHeadline(offer)}</p>
              <p className="text-sm font-medium">{offer.title}</p>
              <p className="text-muted-foreground text-xs">
                {OFFER_TYPE_LABEL[offer.offer_type]}
                {until && ` · ${until}`}
              </p>
              {detail?.description && (
                <p className="text-muted-foreground mt-1 text-sm">{detail.description}</p>
              )}
              {detail?.terms && (
                <p className="text-muted-foreground mt-1 text-xs">Terms: {detail.terms}</p>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-muted-foreground mt-4 text-xs">
        Our AI agent can tell you how an offer applies before you book a viewing.
      </p>
    </section>
  );
}
