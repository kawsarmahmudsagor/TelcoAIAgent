import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import { BrandMark } from '@/components/brand/brand-mark';
import { OpenChatButton } from '@/components/chat-bubble/open-chat-button';
import { ListingCard } from '@/components/home/listing-card';
import { SiteFooter } from '@/components/home/site-footer';
import { SiteNav } from '@/components/home/site-nav';
import {
  ClearFiltersButton,
  PropertyBrowser,
  PropertyFiltersSheet,
  PropertyFiltersSidebar,
  PropertyResults,
  PropertySortSelect,
} from '@/components/properties/property-filters';
import { Button } from '@/components/ui/button';
import {
  PROPERTIES_PAGE_SIZE,
  type PropertyFilters,
  activeFilterCount,
  parsePropertyFilters,
  propertiesHref,
} from '@/lib/property-filters';
import { browseListings, getListingFacets } from '@/lib/public-listings';
import { cn } from '@/lib/shadcn/utils';
import type { PublicListingPage } from '@/lib/types';

const DESCRIPTION =
  'Every flat, house, office and plot Horizon Realty holds across Dhaka, to rent or to buy. Filter by area, price and bedrooms.';

export const metadata: Metadata = {
  title: { absolute: 'All properties | Horizon Realty' },
  description: DESCRIPTION,
  openGraph: {
    type: 'website',
    siteName: 'Horizon Realty',
    title: 'All properties | Horizon Realty',
    description: DESCRIPTION,
    locale: 'en_BD',
  },
};

const CONTAINER = 'mx-auto max-w-6xl px-4 sm:px-8';
const count = new Intl.NumberFormat('en-IN');

export default async function PropertiesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filters = parsePropertyFilters(await searchParams);
  const [page, facets] = await Promise.all([browseListings(filters), getListingFacets()]);
  const total = page?.total ?? null;

  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#results"
        className="bg-primary text-primary-foreground sr-only z-50 rounded-md px-4 py-2 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to results
      </a>
      <SiteNav />
      <PropertyBrowser filters={filters} facets={facets} total={total}>
        <main id="main" className="flex-1">
          <header className="border-b">
            <div className={cn(CONTAINER, 'py-10 sm:py-14')}>
              <nav aria-label="Breadcrumb" className="text-muted-foreground text-sm">
                <Link
                  href="/home"
                  className="hover:text-foreground underline-offset-4 hover:underline"
                >
                  Home
                </Link>
                <span aria-hidden="true" className="mx-2">
                  /
                </span>
                <span aria-current="page">All properties</span>
              </nav>
              <h1 className="font-display mt-3 text-3xl leading-tight font-semibold tracking-[-0.02em] text-balance sm:text-[2.75rem]">
                All properties
              </h1>
              <p className="text-muted-foreground mt-3 max-w-2xl text-base leading-relaxed text-pretty sm:text-lg">
                Every home, office and plot we hold, featured or not. Narrow it down here, or tell
                our AI agent what you need and let it shortlist for you.
              </p>
            </div>
          </header>

          <div
            className={cn(
              CONTAINER,
              'grid gap-8 py-8 sm:py-10 lg:grid-cols-[16.5rem_minmax(0,1fr)] lg:gap-10'
            )}
          >
            <aside className="hidden lg:block">
              <div className="sticky top-24 max-h-[calc(100svh-7rem)] overflow-y-auto pr-1 pb-6">
                <PropertyFiltersSidebar />
              </div>
            </aside>

            <section id="results" aria-labelledby="results-title" className="scroll-mt-20">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="results-title" aria-live="polite" className="text-sm font-medium">
                  <ResultSummary page={page} />
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="lg:hidden">
                    <PropertyFiltersSheet />
                  </div>
                  <PropertySortSelect />
                </div>
              </div>

              <PropertyResults>
                <Results page={page} filters={filters} />
              </PropertyResults>
            </section>
          </div>
        </main>
      </PropertyBrowser>
      <SiteFooter />
    </div>
  );
}

function ResultSummary({ page }: { page: PublicListingPage | null }) {
  if (!page) return <span>Listings unavailable</span>;
  if (page.total === 0) return <span>No matching homes</span>;
  const from = Math.min(page.offset + 1, page.total);
  const to = Math.min(page.offset + page.items.length, page.total);
  if (page.items.length === 0) {
    return <span className="tabular-nums">{count.format(page.total)} homes</span>;
  }
  return (
    <span className="tabular-nums">
      Showing {count.format(from)}–{count.format(to)} of {count.format(page.total)}{' '}
      {page.total === 1 ? 'home' : 'homes'}
    </span>
  );
}

function Results({ page, filters }: { page: PublicListingPage | null; filters: PropertyFilters }) {
  if (!page) {
    return (
      <div className="bg-card mt-6 flex flex-col gap-6 rounded-lg border p-8 sm:flex-row sm:items-center sm:p-10">
        <BrandMark className="text-primary size-12" />
        <div className="flex-1">
          <p className="font-display text-xl font-semibold">Listings aren’t loading right now</p>
          <p className="text-muted-foreground mt-2 max-w-xl">
            Our AI agent can still search every listing we hold and book a viewing for you.
          </p>
        </div>
        <OpenChatButton size="lg" className="self-start sm:self-auto">
          Ask our AI agent
        </OpenChatButton>
      </div>
    );
  }

  const pageCount = Math.max(1, Math.ceil(page.total / PROPERTIES_PAGE_SIZE));

  if (page.items.length === 0) {
    const pastTheEnd = page.total > 0;
    return (
      <div className="mt-6 rounded-lg border border-dashed p-8 sm:p-10">
        <p className="font-display text-xl font-semibold">
          {pastTheEnd ? 'There’s nothing on this page' : 'No homes match these filters'}
        </p>
        <p className="text-muted-foreground mt-2 max-w-lg">
          {pastTheEnd
            ? `These filters have ${pageCount} ${pageCount === 1 ? 'page' : 'pages'} of results.`
            : 'Try fewer filters or a wider price range. Our agent also hears about homes before they’re listed.'}
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          {pastTheEnd ? (
            <Button asChild>
              <Link href={propertiesHref({ ...filters, page: 1 })}>Back to page 1</Link>
            </Button>
          ) : (
            <>
              {activeFilterCount(filters) > 0 && (
                <ClearFiltersButton className="border-input bg-card text-foreground h-9 border px-4" />
              )}
              <OpenChatButton>Ask our AI agent</OpenChatButton>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <>
      <ul className="mt-6 grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
        {page.items.map((listing, i) => (
          <li key={listing.id} className="flex">
            <ListingCard listing={listing} priority={i < 3} />
          </li>
        ))}
      </ul>
      {pageCount > 1 && (
        <Pagination filters={filters} current={filters.page} pageCount={pageCount} />
      )}
    </>
  );
}

/** Page numbers to show: the first, the last, and two either side of the current one. */
function pageWindow(current: number, pageCount: number): (number | 'gap')[] {
  const pages = new Set([1, pageCount]);
  for (let p = current - 2; p <= current + 2; p++) {
    if (p >= 1 && p <= pageCount) pages.add(p);
  }
  const sorted = [...pages].sort((a, b) => a - b);
  const out: (number | 'gap')[] = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push('gap');
    out.push(p);
  });
  return out;
}

function Pagination({
  filters,
  current,
  pageCount,
}: {
  filters: PropertyFilters;
  current: number;
  pageCount: number;
}) {
  const href = (p: number) => `${propertiesHref({ ...filters, page: p })}#results`;
  const step =
    'focus-visible:ring-ring/50 inline-flex h-10 items-center gap-1 rounded-full border px-3 text-sm font-medium outline-none focus-visible:ring-[3px]';
  return (
    <nav aria-label="Pages" className="mt-10 flex flex-wrap items-center justify-center gap-2">
      {current > 1 ? (
        <Link href={href(current - 1)} className={cn(step, 'bg-card hover:bg-accent')}>
          <ChevronLeftIcon aria-hidden="true" className="size-4" />
          Previous
        </Link>
      ) : (
        <span aria-hidden="true" className={cn(step, 'text-muted-foreground/60')}>
          <ChevronLeftIcon className="size-4" />
          Previous
        </span>
      )}
      <ol className="hidden items-center gap-1 sm:flex">
        {pageWindow(current, pageCount).map((p, i) =>
          p === 'gap' ? (
            <li key={`gap-${i}`} aria-hidden="true" className="text-muted-foreground px-1">
              …
            </li>
          ) : (
            <li key={p}>
              <Link
                href={href(p)}
                aria-current={p === current ? 'page' : undefined}
                aria-label={`Page ${p}`}
                className={cn(
                  'focus-visible:ring-ring/50 grid size-10 place-items-center rounded-full text-sm font-medium tabular-nums outline-none focus-visible:ring-[3px]',
                  p === current ? 'bg-foreground text-background' : 'hover:bg-accent'
                )}
              >
                {p}
              </Link>
            </li>
          )
        )}
      </ol>
      <span className="text-muted-foreground px-2 text-sm tabular-nums sm:hidden">
        Page {current} of {pageCount}
      </span>
      {current < pageCount ? (
        <Link href={href(current + 1)} className={cn(step, 'bg-card hover:bg-accent')}>
          Next
          <ChevronRightIcon aria-hidden="true" className="size-4" />
        </Link>
      ) : (
        <span aria-hidden="true" className={cn(step, 'text-muted-foreground/60')}>
          Next
          <ChevronRightIcon className="size-4" />
        </span>
      )}
    </nav>
  );
}
