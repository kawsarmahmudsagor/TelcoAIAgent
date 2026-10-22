import { type PropertyFilters, browseQuery, propertiesHref } from '@/lib/property-filters';
import type {
  ListingType,
  PropertyType,
  PublicAgentInfo,
  PublicListing,
  PublicListingFacets,
  PublicListingPage,
  PublicOffer,
} from '@/lib/types';

// Server-side only: the landing page talks to FastAPI directly rather than through the
// `/backend` rewrite. `||` so an empty build arg still falls back to the local dev API.
const API_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8011';

/**
 * Featured listings for the public landing page, or `null` when the API can't be reached
 * (the page then shows its empty state instead of failing). Cached for 60 seconds.
 */
export async function getFeaturedListings(limit = 24): Promise<PublicListing[] | null> {
  try {
    const res = await fetch(`${API_URL}/api/public/listings?limit=${limit}&featured=true`, {
      signal: AbortSignal.timeout(3000),
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    const data: unknown = await res.json();
    return Array.isArray(data) ? (data as PublicListing[]) : null;
  } catch {
    return null;
  }
}

/**
 * One page of every active listing for the "all properties" page, or `null` when the API can't
 * be reached. Cached for 60 seconds per filter combination.
 */
export async function browseListings(filters: PropertyFilters): Promise<PublicListingPage | null> {
  try {
    const res = await fetch(`${API_URL}/api/public/listings/browse?${browseQuery(filters)}`, {
      signal: AbortSignal.timeout(3000),
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as PublicListingPage;
    return Array.isArray(data?.items) ? data : null;
  } catch {
    return null;
  }
}

/** The filter options for the "all properties" page, or `null` when the API can't be reached. */
export async function getListingFacets(): Promise<PublicListingFacets | null> {
  try {
    const res = await fetch(`${API_URL}/api/public/listings/facets`, {
      signal: AbortSignal.timeout(3000),
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    return (await res.json()) as PublicListingFacets;
  } catch {
    return null;
  }
}

/**
 * One active listing for its property page. `'not-found'` when the API says 404 (missing,
 * deactivated or a malformed id), `null` when the API can't be reached. Cached for 60 seconds.
 */
export async function getListing(id: string): Promise<PublicListing | 'not-found' | null> {
  try {
    const res = await fetch(`${API_URL}/api/public/listings/${encodeURIComponent(id)}`, {
      signal: AbortSignal.timeout(3000),
      next: { revalidate: 60 },
    });
    if (res.status === 404) return 'not-found';
    if (!res.ok) return null;
    return (await res.json()) as PublicListing;
  } catch {
    return null;
  }
}

/** The agent's display names, or `null` when the API can't be reached. Cached for 5 minutes. */
export async function getAgentInfo(): Promise<PublicAgentInfo | null> {
  try {
    const res = await fetch(`${API_URL}/api/public/agent-info`, {
      signal: AbortSignal.timeout(3000),
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return (await res.json()) as PublicAgentInfo;
  } catch {
    return null;
  }
}

/** Live offers for the public site, or `null` when the API can't be reached. Cached for 60 s. */
export async function getLiveOffers(): Promise<PublicOffer[] | null> {
  try {
    const res = await fetch(`${API_URL}/api/public/offers`, {
      signal: AbortSignal.timeout(3000),
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    const data: unknown = await res.json();
    return Array.isArray(data) ? (data as PublicOffer[]) : null;
  } catch {
    return null;
  }
}

/** The landing page's rent/sale filter (`?listing=`). */
export const HOME_LISTING_TYPES = [
  { slug: 'sale', label: 'For sale' },
  { slug: 'rent', label: 'To rent' },
] as const satisfies readonly { slug: ListingType; label: string }[];

export function homeListingTypeOf(slug: string | undefined) {
  return HOME_LISTING_TYPES.find((t) => t.slug === slug);
}

/** `/home?type=…&listing=…#homes`, leaving out whichever filter is unset. */
export function homeFilterHref(filters: { type?: string; listing?: string }): string {
  const params = new URLSearchParams();
  if (filters.type) params.set('type', filters.type);
  if (filters.listing) params.set('listing', filters.listing);
  const query = params.toString();
  return `/home${query ? `?${query}` : ''}#homes`;
}

/** The landing page's "browse by type" groups. Flats include studios. */
export const HOME_TYPES = [
  {
    slug: 'flat',
    label: 'Flats',
    types: ['apartment', 'studio'],
    blurb: 'Studios to four-bedroom family flats, to rent or to buy.',
  },
  {
    slug: 'duplex',
    label: 'Duplexes',
    types: ['duplex'],
    blurb: 'Two floors joined by an inside staircase, often with a terrace.',
  },
  {
    slug: 'commercial',
    label: 'Commercial',
    types: ['commercial'],
    blurb: 'Office floors, suites and street-front shops.',
  },
  {
    slug: 'plot',
    label: 'Plots',
    types: ['plot'],
    blurb: 'Residential and commercial land, measured in katha.',
  },
] as const satisfies readonly {
  slug: string;
  label: string;
  types: readonly PropertyType[];
  blurb: string;
}[];

export type HomeTypeSlug = (typeof HOME_TYPES)[number]['slug'];

export function homeTypeOf(slug: string | undefined) {
  return HOME_TYPES.find((t) => t.slug === slug);
}

export function inHomeType(listing: PublicListing, slug: HomeTypeSlug): boolean {
  const group = homeTypeOf(slug);
  return !!group && (group.types as readonly PropertyType[]).includes(listing.property_type);
}

/**
 * Up to `count` listings for the unfiltered grid, one of each property type first so the grid
 * shows the range rather than six flats in a row.
 */
export function pickVaried(listings: PublicListing[], count: number): PublicListing[] {
  const seen = new Set<PropertyType>();
  const first: PublicListing[] = [];
  const rest: PublicListing[] = [];
  for (const l of listings) {
    if (seen.has(l.property_type)) rest.push(l);
    else {
      seen.add(l.property_type);
      first.push(l);
    }
  }
  return [...first, ...rest].slice(0, count);
}

/** `/properties` with the landing page's current type group and rent/sale filter carried over. */
export function exploreAllHref(filters: { type?: string; listing?: string }): string {
  const group = homeTypeOf(filters.type);
  const listing = homeListingTypeOf(filters.listing);
  return propertiesHref({ types: group ? [...group.types] : [], listing: listing?.slug });
}
