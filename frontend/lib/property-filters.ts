import type { ListingType, PropertyType } from '@/lib/types';

/**
 * The "all properties" page's filters, kept in its query string so a search can be shared and
 * the back button steps through it. Safe to import from client components.
 *
 * `/properties?listing=sale&type=house&type=duplex&area=Gulshan&min=…&max=…&beds=3&baths=2&sort=price_asc&page=2`
 */
export interface PropertyFilters {
  listing?: ListingType;
  types: PropertyType[];
  area?: string;
  min?: number;
  max?: number;
  beds?: number;
  baths?: number;
  sort: PropertySort;
  page: number;
}

export const PROPERTIES_PAGE_SIZE = 12;

export const PROPERTY_SORTS = [
  { value: 'featured', label: 'Featured first' },
  { value: 'newest', label: 'Newest' },
  { value: 'price_asc', label: 'Price: low to high' },
  { value: 'price_desc', label: 'Price: high to low' },
] as const;

export type PropertySort = (typeof PROPERTY_SORTS)[number]['value'];

/** In the order the filter shows them. */
export const PROPERTY_TYPE_OPTIONS = [
  'apartment',
  'studio',
  'duplex',
  'commercial',
  'plot',
] as const satisfies readonly PropertyType[];

export const LISTING_OPTIONS = [
  { value: 'sale', label: 'For sale' },
  { value: 'rent', label: 'To rent' },
] as const satisfies readonly { value: ListingType; label: string }[];

export const BEDROOM_OPTIONS = [1, 2, 3, 4, 5] as const;
export const BATHROOM_OPTIONS = [1, 2, 3, 4] as const;

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function all(value: string | string[] | undefined): string[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

/** A non-negative number, or undefined for anything else (so a bad link just drops the filter). */
function amount(value: string | undefined, integer = false): number | undefined {
  if (!value) return undefined;
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return undefined;
  return integer ? Math.floor(n) : n;
}

/** Reads the filters from a query string, ignoring anything unknown or malformed. */
export function parsePropertyFilters(params: SearchParams): PropertyFilters {
  const listing = first(params.listing);
  const sort = first(params.sort);
  const types = all(params.type).filter((t): t is PropertyType =>
    (PROPERTY_TYPE_OPTIONS as readonly string[]).includes(t)
  );
  let min = amount(first(params.min));
  let max = amount(first(params.max));
  if (min !== undefined && max !== undefined && min > max) [min, max] = [max, min];
  const beds = amount(first(params.beds), true);
  const baths = amount(first(params.baths), true);
  return {
    listing: LISTING_OPTIONS.some((o) => o.value === listing)
      ? (listing as ListingType)
      : undefined,
    types: [...new Set(types)],
    area: first(params.area)?.trim() || undefined,
    min,
    max,
    beds: beds || undefined,
    baths: baths || undefined,
    sort: PROPERTY_SORTS.some((s) => s.value === sort) ? (sort as PropertySort) : 'featured',
    page: Math.max(1, amount(first(params.page), true) || 1),
  };
}

/** `/properties?…` for these filters, leaving out defaults so links stay short. */
export function propertiesHref(filters: Partial<PropertyFilters>): string {
  const params = new URLSearchParams();
  if (filters.listing) params.set('listing', filters.listing);
  for (const t of filters.types ?? []) params.append('type', t);
  if (filters.area) params.set('area', filters.area);
  if (filters.min !== undefined) params.set('min', String(filters.min));
  if (filters.max !== undefined) params.set('max', String(filters.max));
  if (filters.beds) params.set('beds', String(filters.beds));
  if (filters.baths) params.set('baths', String(filters.baths));
  if (filters.sort && filters.sort !== 'featured') params.set('sort', filters.sort);
  if (filters.page && filters.page > 1) params.set('page', String(filters.page));
  const query = params.toString();
  return `/properties${query ? `?${query}` : ''}`;
}

/** The query `GET /api/public/listings/browse` takes for one page of these filters. */
export function browseQuery(filters: PropertyFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.listing) params.set('listing_type', filters.listing);
  for (const t of filters.types) params.append('property_type', t);
  if (filters.area) params.set('area', filters.area);
  if (filters.min !== undefined) params.set('min_price', String(filters.min));
  if (filters.max !== undefined) params.set('max_price', String(filters.max));
  if (filters.beds) params.set('min_bedrooms', String(filters.beds));
  if (filters.baths) params.set('min_bathrooms', String(filters.baths));
  params.set('sort', filters.sort);
  params.set('limit', String(PROPERTIES_PAGE_SIZE));
  params.set('offset', String((filters.page - 1) * PROPERTIES_PAGE_SIZE));
  return params;
}

/** How many filters are set (sort and page don't count). */
export function activeFilterCount(filters: PropertyFilters): number {
  return (
    (filters.listing ? 1 : 0) +
    (filters.types.length ? 1 : 0) +
    (filters.area ? 1 : 0) +
    (filters.min !== undefined || filters.max !== undefined ? 1 : 0) +
    (filters.beds ? 1 : 0) +
    (filters.baths ? 1 : 0)
  );
}
