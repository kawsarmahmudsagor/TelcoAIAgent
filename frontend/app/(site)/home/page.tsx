import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRightIcon,
  ArrowUpRightIcon,
  CalendarCheckIcon,
  KeyRoundIcon,
  MessageSquareTextIcon,
  MicIcon,
  PhoneCallIcon,
  ScrollTextIcon,
  ShieldCheckIcon,
  WalletIcon,
} from 'lucide-react';
import { BrandMark } from '@/components/brand/brand-mark';
import { Skyline } from '@/components/brand/skyline';
import { OpenChatButton } from '@/components/chat-bubble/open-chat-button';
import { ListingCard } from '@/components/home/listing-card';
import { PropertyPhoto } from '@/components/home/property-photo';
import { SiteFooter } from '@/components/home/site-footer';
import { SiteNav } from '@/components/home/site-nav';
import { OfferCard } from '@/components/offers/offer-card';
import { Button } from '@/components/ui/button';
import {
  HOME_LISTING_TYPES,
  HOME_TYPES,
  exploreAllHref,
  getFeaturedListings,
  getLiveOffers,
  homeFilterHref,
  homeListingTypeOf,
  homeTypeOf,
  inHomeType,
  pickVaried,
} from '@/lib/public-listings';
import { cn } from '@/lib/shadcn/utils';
import type { PublicListing, PublicOffer } from '@/lib/types';

const unsplash = (id: string, w = 1200) =>
  `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&q=80`;

// Same verified photo IDs as backend/app/data/listing_images.py.
const HERO_PHOTO = unsplash('1600607687939-ce8a6c25118c', 1600);

const DESCRIPTION =
  'Flats, duplexes, offices and plots across Dhaka. Ask our AI agent by chat, voice or phone, and book a viewing with the Horizon Realty team.';

export const metadata: Metadata = {
  title: { absolute: 'Horizon Realty | Flats and homes in Dhaka' },
  description: DESCRIPTION,
  openGraph: {
    type: 'website',
    siteName: 'Horizon Realty',
    title: 'Horizon Realty | Flats and homes in Dhaka',
    description: DESCRIPTION,
    locale: 'en_BD',
    images: [{ url: unsplash('1600607687939-ce8a6c25118c', 1200), width: 1200, height: 800 }],
  },
  twitter: { card: 'summary_large_image' },
};

const AREAS = [
  {
    name: 'Gulshan',
    blurb: 'Lakeside towers, embassies and the city’s busiest office avenue.',
    photo: unsplash('1486406146926-c627a92ad1ab', 900),
  },
  {
    name: 'Banani',
    blurb: 'Restaurants along Road 11 and quiet lanes running down to the lake.',
    photo: unsplash('1545324418-cc1a3fa10c00', 900),
  },
  {
    name: 'Dhanmondi',
    blurb: 'Old trees, the lake path and family flats close to good schools.',
    photo: unsplash('1515263487990-61b07816b324', 900),
  },
  {
    name: 'Uttara',
    blurb: 'Planned sectors near the airport, with lakes and wide roads.',
    photo: unsplash('1574362848149-11496d93a7c7', 900),
  },
  {
    name: 'Bashundhara R/A',
    match: 'Bashundhara',
    blurb: 'Gated blocks around the universities, a short drive from Gulshan.',
    photo: unsplash('1551361415-69c87624334f', 900),
  },
  {
    name: 'Purbachal',
    blurb: 'The new town east of the city, where good plots are still open.',
    photo: unsplash('1500382017468-9049fed747ef', 900),
  },
];

const CHANNELS = [
  {
    icon: MessageSquareTextIcon,
    title: 'Chat',
    body: 'Type what you’re after: area, budget, bedrooms. The agent replies in seconds with homes that fit, photos included.',
  },
  {
    icon: MicIcon,
    title: 'Talk by voice',
    body: 'Press the mic and speak to it the way you’d ring our office. It answers at any hour.',
  },
  {
    icon: PhoneCallIcon,
    title: 'Take a phone call',
    body: 'Leave your number and the agent calls you back to go through the options when it suits you.',
  },
  {
    icon: CalendarCheckIcon,
    title: 'Book a viewing',
    body: 'When a place looks right, it books a visit with one of our agents and confirms the time.',
  },
];

const PROMISES = [
  {
    icon: KeyRoundIcon,
    title: 'Every home visited',
    body: 'Someone from our team has walked through each featured listing.',
  },
  {
    icon: ScrollTextIcon,
    title: 'Papers checked',
    body: 'We confirm approvals and ownership documents before a sale goes live.',
  },
  {
    icon: ShieldCheckIcon,
    title: 'Straight answers',
    body: 'Prices, service charges and availability, told plainly from the start.',
  },
  {
    icon: WalletIcon,
    title: 'Free to ask',
    body: 'Questions, call-backs and viewings cost you nothing.',
  },
];

const GRID_SIZE = 6;
const CONTAINER = 'mx-auto max-w-6xl px-4 sm:px-8';

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string | string[]; listing?: string | string[] }>;
}) {
  const params = await searchParams;
  const activeType = homeTypeOf(typeof params.type === 'string' ? params.type : undefined);
  const activeListing = homeListingTypeOf(
    typeof params.listing === 'string' ? params.listing : undefined
  );
  const [listings, offers] = await Promise.all([getFeaturedListings(), getLiveOffers()]);

  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#main"
        className="bg-primary text-primary-foreground sr-only z-50 rounded-md px-4 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <SiteNav />
      <main id="main" className="flex-1">
        <Hero />
        <FeaturedHomes
          listings={listings}
          activeSlug={activeType?.slug}
          activeListing={activeListing?.slug}
        />
        <Offers offers={offers} />
        <BrowseByType listings={listings} />
        <HowItWorks />
        <Areas listings={listings} />
        <Promises />
        <Contact />
      </main>
      <SiteFooter />
    </div>
  );
}

function SectionHeading({
  id,
  title,
  children,
  className,
}: {
  id: string;
  title: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('max-w-2xl', className)}>
      <h2
        id={id}
        className="font-display text-3xl leading-tight font-semibold tracking-[-0.02em] text-balance sm:text-4xl"
      >
        {title}
      </h2>
      {children && (
        <p className="text-muted-foreground mt-3 text-base leading-relaxed text-pretty sm:text-lg">
          {children}
        </p>
      )}
    </div>
  );
}

function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="bg-sidebar text-sidebar-foreground relative overflow-hidden"
    >
      <div
        className={cn(
          CONTAINER,
          'grid pt-12 sm:pt-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:grid-rows-[1fr_auto] lg:gap-x-14 lg:pt-20'
        )}
      >
        <div className="lg:self-center lg:pb-10">
          <h1
            id="hero-title"
            className="font-display text-[2.5rem] leading-[1.02] font-semibold tracking-[-0.03em] text-balance sm:text-6xl lg:text-[4.25rem]"
          >
            A home in Dhaka, one conversation away.
          </h1>
          <p className="text-sidebar-foreground/80 mt-6 max-w-xl text-lg leading-relaxed text-pretty">
            Tell our AI agent the area, the budget and how many bedrooms, by chat, by voice or over
            a phone call. It knows every listing we hold and books your viewing with our team.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <OpenChatButton
              size="lg"
              className="bg-sidebar-foreground text-sidebar hover:bg-sidebar-foreground/90 focus-visible:ring-sidebar-ring/60 h-12 px-6 text-base"
            >
              Talk to our AI agent
            </OpenChatButton>
            <Button
              asChild
              size="lg"
              variant="ghost"
              className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:ring-sidebar-ring/60 h-12 border border-white/25 px-6 text-base"
            >
              <a href="#homes">See featured homes</a>
            </Button>
          </div>
        </div>
        <div className="relative mt-10 aspect-[4/3] overflow-hidden rounded-xl sm:aspect-[16/10] lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:mt-0 lg:aspect-[5/6] lg:self-end lg:rounded-b-none">
          <PropertyPhoto
            src={HERO_PHOTO}
            alt="A bright living room with tall windows, sofas and a dining table"
            sizes="(min-width: 1024px) 560px, 100vw"
            priority
          />
        </div>
        {/* Dhaka at dusk, standing on the same baseline as the photo. Full-bleed on phones. */}
        <Skyline className="-mx-4 mt-6 aspect-[600/230] w-[calc(100%+2rem)] sm:-mx-8 sm:w-[calc(100%+4rem)] lg:col-start-1 lg:row-start-2 lg:mx-0 lg:mt-0 lg:w-full" />
      </div>
    </section>
  );
}

function FeaturedHomes({
  listings,
  activeSlug,
  activeListing,
}: {
  listings: PublicListing[] | null;
  activeSlug: string | undefined;
  activeListing: string | undefined;
}) {
  const active = homeTypeOf(activeSlug);
  const listingType = homeListingTypeOf(activeListing);
  const filtered = !listings
    ? []
    : listings.filter(
        (l) =>
          (!active || inHomeType(l, active.slug)) &&
          (!listingType || l.listing_type === listingType.slug)
      );
  const shown = active || listingType ? filtered : pickVaried(filtered, GRID_SIZE);
  const emptyLabel = [active?.label.toLowerCase() ?? 'homes', listingType?.label.toLowerCase()]
    .filter(Boolean)
    .join(' ');
  // Carries the chosen type and rent/sale over to the full list.
  const exploreHref = exploreAllHref({ type: active?.slug, listing: listingType?.slug });

  return (
    <section aria-labelledby="homes-title" id="homes" className="scroll-mt-16 py-20 sm:py-24">
      <div className={CONTAINER}>
        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
          <SectionHeading id="homes-title" title="Featured homes">
            Hand-picked flats, family homes and workspaces our team has visited this season.
          </SectionHeading>
          <Button asChild variant="outline" size="lg" className="hidden h-11 px-5 sm:inline-flex">
            <Link href={exploreHref}>
              Explore all
              <ArrowRightIcon aria-hidden="true" />
            </Link>
          </Button>
        </div>

        {listings && listings.length > 0 && (
          <nav
            aria-label="Filter featured homes by type"
            className="-mx-4 mt-8 overflow-x-auto px-4 sm:mx-0 sm:px-0"
          >
            <ul className="flex gap-2 pb-1">
              <FilterLink
                href={homeFilterHref({ listing: listingType?.slug })}
                current={!active}
                label="All"
              />
              {HOME_TYPES.map((t) => (
                <FilterLink
                  key={t.slug}
                  href={homeFilterHref({ type: t.slug, listing: listingType?.slug })}
                  current={active?.slug === t.slug}
                  label={t.label}
                />
              ))}
              <li aria-hidden="true" className="bg-border mx-1 w-px shrink-0 self-stretch" />
              {HOME_LISTING_TYPES.map((t) => (
                <FilterLink
                  key={t.slug}
                  // Picking the current one again clears it.
                  href={homeFilterHref({
                    type: active?.slug,
                    listing: listingType?.slug === t.slug ? undefined : t.slug,
                  })}
                  current={listingType?.slug === t.slug}
                  label={t.label}
                />
              ))}
            </ul>
          </nav>
        )}

        {listings === null || listings.length === 0 ? (
          <EmptyListings unavailable={listings === null} />
        ) : shown.length === 0 ? (
          <div className="mt-8 rounded-lg border border-dashed p-8 sm:p-10">
            <p className="font-display text-xl font-semibold">No featured {emptyLabel} right now</p>
            <p className="text-muted-foreground mt-2 max-w-lg">
              Our agent can search everything we hold, including homes that aren’t featured here.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <OpenChatButton>Ask our AI agent</OpenChatButton>
              <Button asChild variant="outline">
                <Link href={exploreHref}>Explore all {emptyLabel}</Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/home#homes">Show all featured homes</Link>
              </Button>
            </div>
          </div>
        ) : (
          <>
            <ul className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((listing, i) => (
                <li key={listing.id} className="flex">
                  <ListingCard listing={listing} priority={i < 3} />
                </li>
              ))}
            </ul>
            {/* Phones: the header button is hidden, so the way on sits under the grid. */}
            <Button asChild variant="outline" size="lg" className="mt-8 h-11 w-full sm:hidden">
              <Link href={exploreHref}>
                Explore all homes
                <ArrowRightIcon aria-hidden="true" />
              </Link>
            </Button>
          </>
        )}
      </div>
    </section>
  );
}

function Offers({ offers }: { offers: PublicOffer[] | null }) {
  if (!offers?.length) return null;
  return (
    <section aria-labelledby="offers-title" id="offers" className="scroll-mt-16 pb-20 sm:pb-24">
      <div className={CONTAINER}>
        <SectionHeading id="offers-title" title="Current offers">
          Discounts and easier payment terms on homes for sale. Ask our agent how they apply to the
          home you like.
        </SectionHeading>
        <ul className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {offers.map((offer) => (
            <li key={offer.id} className="flex">
              <OfferCard offer={offer} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function FilterLink({ href, current, label }: { href: string; current: boolean; label: string }) {
  return (
    <li className="shrink-0">
      <Link
        href={href}
        scroll={false}
        aria-current={current ? 'true' : undefined}
        className={cn(
          'focus-visible:ring-ring/50 inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px]',
          current
            ? 'bg-foreground text-background border-foreground'
            : 'bg-card text-foreground hover:bg-accent'
        )}
      >
        {label}
      </Link>
    </li>
  );
}

function EmptyListings({ unavailable }: { unavailable: boolean }) {
  return (
    <div className="bg-card mt-8 flex flex-col gap-6 rounded-lg border p-8 sm:flex-row sm:items-center sm:p-10">
      <BrandMark className="text-primary size-12" />
      <div className="flex-1">
        <p className="font-display text-xl font-semibold">
          {unavailable ? 'Featured homes aren’t loading right now' : 'New homes are on the way'}
        </p>
        <p className="text-muted-foreground mt-2 max-w-xl">
          {unavailable
            ? 'Our AI agent can still search every listing we hold and book a viewing for you.'
            : 'Our team is visiting the next set of featured homes. Meanwhile the agent can search everything we hold.'}
        </p>
      </div>
      <OpenChatButton size="lg" className="self-start sm:self-auto">
        Ask our AI agent
      </OpenChatButton>
    </div>
  );
}

function BrowseByType({ listings }: { listings: PublicListing[] | null }) {
  return (
    <section aria-labelledby="types-title" className="bg-muted/60 border-y py-20 sm:py-24">
      <div className={CONTAINER}>
        <SectionHeading id="types-title" title="Browse by type">
          From a studio near your office to a plot for the family home you’ll build later.
        </SectionHeading>
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {HOME_TYPES.map((t, i) => {
            const count = listings?.filter((l) => inHomeType(l, t.slug)).length;
            return (
              <li
                key={t.slug}
                className={cn(
                  'flex',
                  // Odd card count on tablets: let the last one span the row.
                  i === HOME_TYPES.length - 1 && 'sm:max-lg:col-span-2'
                )}
              >
                <Link
                  href={`/home?type=${t.slug}#homes`}
                  className="group bg-card hover:border-primary/40 focus-visible:ring-ring/50 flex w-full flex-col gap-3 rounded-3xl border p-6 shadow-sm transition-[transform,box-shadow,border-color] duration-200 outline-none hover:-translate-y-1 hover:shadow-lg focus-visible:ring-[3px] motion-reduce:transition-none motion-reduce:hover:translate-y-0"
                >
                  <span className="flex items-start justify-between gap-2">
                    <span className="font-display text-xl font-semibold tracking-[-0.01em]">
                      {t.label}
                    </span>
                    <span
                      aria-hidden
                      className="bg-muted text-foreground group-hover:bg-primary group-hover:text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-full transition-colors"
                    >
                      <ArrowUpRightIcon className="size-4" />
                    </span>
                  </span>
                  <span className="text-muted-foreground text-sm leading-relaxed">{t.blurb}</span>
                  {count !== undefined && (
                    <span className="bg-primary/10 text-primary mt-auto w-fit rounded-full px-3 py-1 text-sm font-medium tabular-nums">
                      {count === 0
                        ? 'Ask about upcoming listings'
                        : `${count} featured ${count === 1 ? 'listing' : 'listings'}`}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section aria-labelledby="how-title" id="how-it-works" className="scroll-mt-16 py-20 sm:py-24">
      <div className={cn(CONTAINER, 'grid gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]')}>
        <div className="lg:sticky lg:top-28 lg:self-start">
          <SectionHeading id="how-title" title="Ask the way that suits you">
            Our AI agent works from the same listings our staff do. It answers questions about a
            home or an area, narrows down a shortlist with you, and hands over to a person when it’s
            time to visit.
          </SectionHeading>
          <OpenChatButton size="lg" className="mt-8">
            Start a conversation
          </OpenChatButton>
        </div>
        <ul className="divide-y border-y">
          {CHANNELS.map(({ icon: Icon, title, body }) => (
            <li key={title} className="flex gap-5 py-7">
              <span className="bg-primary/10 text-primary grid size-11 shrink-0 place-items-center rounded-md">
                <Icon aria-hidden="true" className="size-5" />
              </span>
              <div>
                <h3 className="font-display text-xl font-semibold tracking-[-0.01em]">{title}</h3>
                <p className="text-muted-foreground mt-1.5 leading-relaxed">{body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Areas({ listings }: { listings: PublicListing[] | null }) {
  return (
    <section aria-labelledby="areas-title" id="areas" className="scroll-mt-16 pb-20 sm:pb-24">
      <div className={CONTAINER}>
        <SectionHeading id="areas-title" title="Neighbourhoods we know well">
          Our agents live and work in these parts of the city, and visit every home before it’s
          listed.
        </SectionHeading>
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {AREAS.map((area) => {
            const key = area.match ?? area.name;
            const count = listings?.filter((l) => l.neighborhood?.startsWith(key)).length ?? 0;
            return (
              <li
                key={area.name}
                className="relative isolate flex aspect-[16/11] flex-col justify-end overflow-hidden rounded-lg p-5 text-white sm:aspect-[4/3]"
              >
                <PropertyPhoto
                  src={area.photo}
                  alt=""
                  sizes="(min-width: 1024px) 360px, (min-width: 640px) 50vw, 100vw"
                  className="-z-10"
                />
                {/* Darkens the lower half so the white text holds 4.5:1 on any photo. */}
                <div
                  aria-hidden="true"
                  className="absolute inset-0 -z-10 bg-gradient-to-t from-black/90 via-black/60 via-50% to-black/0"
                />
                <h3 className="font-display text-2xl font-semibold tracking-[-0.015em]">
                  {area.name}
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-white/90">{area.blurb}</p>
                {count > 0 && (
                  <p className="mt-3 text-sm font-medium text-white tabular-nums">
                    <span className="bg-brass mr-2 inline-block size-2 rounded-full align-middle" />
                    {count} featured {count === 1 ? 'home' : 'homes'}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

function Promises() {
  return (
    <section aria-labelledby="promises-title" className="border-y">
      <h2 id="promises-title" className="sr-only">
        What you can expect from us
      </h2>
      <ul className={cn(CONTAINER, 'grid gap-8 py-12 sm:grid-cols-2 lg:grid-cols-4 lg:gap-10')}>
        {PROMISES.map(({ icon: Icon, title, body }) => (
          <li key={title} className="flex gap-4">
            <Icon aria-hidden="true" className="text-brass mt-0.5 size-5 shrink-0" />
            <div>
              <h3 className="font-semibold">{title}</h3>
              <p className="text-muted-foreground mt-1 text-sm leading-relaxed">{body}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Contact() {
  return (
    <section aria-labelledby="contact-title" id="contact" className="scroll-mt-16 py-20 sm:py-24">
      <div className={CONTAINER}>
        <div className="bg-sidebar text-sidebar-foreground border-sidebar-border overflow-hidden rounded-xl dark:border">
          <div className="grid gap-10 p-8 sm:p-12 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:items-end">
            <div>
              <h2
                id="contact-title"
                className="font-display text-3xl leading-tight font-semibold tracking-[-0.02em] text-balance sm:text-[2.75rem]"
              >
                Tell us what you’re looking for.
              </h2>
              <p className="text-sidebar-foreground/80 mt-4 max-w-lg text-lg leading-relaxed">
                The agent can shortlist homes, answer questions about an area and book a viewing for
                this week, tonight if you like.
              </p>
              <OpenChatButton
                size="lg"
                className="bg-sidebar-foreground text-sidebar hover:bg-sidebar-foreground/90 focus-visible:ring-sidebar-ring/60 mt-8 h-12 px-6 text-base"
              >
                Talk to our AI agent
              </OpenChatButton>
            </div>
            <dl className="text-sidebar-foreground/80 grid gap-5 text-sm sm:grid-cols-2 lg:grid-cols-1">
              <div>
                <dt className="text-sidebar-foreground font-semibold">Office</dt>
                <dd className="mt-1">Gulshan 2, Dhaka 1212</dd>
              </div>
              <div>
                <dt className="text-sidebar-foreground font-semibold">Viewings</dt>
                <dd className="mt-1">Saturday to Thursday, 10 am to 7 pm</dd>
              </div>
              <div>
                <dt className="text-sidebar-foreground font-semibold">The AI agent</dt>
                <dd className="mt-1">Open around the clock, by chat, voice or phone</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
