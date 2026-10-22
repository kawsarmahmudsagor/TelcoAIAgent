import type { DateString, UUID } from './common';
import type { ListingOffer } from './offer';
import type { ListingType, PropertyType } from './property';

/** Unauthenticated landing-page listing: no street address, no internal flags. */
export interface PublicListing {
  id: UUID;
  title: string;
  city: string;
  neighborhood: string | null;
  property_type: PropertyType;
  listing_type: ListingType;
  price: number;
  bedrooms: number;
  bathrooms: number;
  sqft: number | null;
  amenities: string[];
  available_from: DateString | null;
  description: string | null;
  image_url: string | null;
  images: string[] | null;
  is_featured: boolean;
  /** Live offers on this listing; always empty for a rental. */
  offers: ListingOffer[];
}

/** The names the agent introduces itself with (`GET /api/public/agent-info`). */
export interface PublicAgentInfo {
  assistant_name: string;
  operator_name: string;
}

export interface PublicListingParams {
  /** Capped at 24 by the backend. Default 6. */
  limit?: number;
  /** Default true: only featured listings. */
  featured?: boolean;
}

/** One page of `GET /api/public/listings/browse`: every active listing, filtered and sorted. */
export interface PublicListingPage {
  items: PublicListing[];
  /** Listings matching the filters across all pages. */
  total: number;
  limit: number;
  offset: number;
}

/** The public listings page's filter options (`GET /api/public/listings/facets`). */
export interface PublicListingFacets {
  total: number;
  cities: { name: string; count: number }[];
  neighborhoods: { name: string; city: string; count: number }[];
  property_types: { value: PropertyType; count: number }[];
  /** Price bounds per listing type: rents and sale prices are on very different scales. */
  price_ranges: { listing_type: ListingType; min: number; max: number; count: number }[];
  max_bedrooms: number;
}
