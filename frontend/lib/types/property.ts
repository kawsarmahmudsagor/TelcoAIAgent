import type { DateString, DateTimeString, UUID } from './common';

export type PropertyType = 'apartment' | 'studio' | 'duplex' | 'commercial' | 'plot';

export type ListingType = 'rent' | 'sale';

export interface Property {
  id: UUID;
  title: string;
  address_line: string;
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
  is_active: boolean;
  is_featured: boolean;
  created_at: DateTimeString;
  updated_at: DateTimeString;
}

export interface PropertyCreate {
  title: string;
  address_line: string;
  city: string;
  neighborhood?: string | null;
  property_type: PropertyType;
  listing_type: ListingType;
  price: number;
  bedrooms: number;
  bathrooms: number;
  sqft?: number | null;
  amenities?: string[];
  available_from?: DateString | null;
  description?: string | null;
  image_url?: string | null;
  images?: string[] | null;
  is_active?: boolean;
  is_featured?: boolean;
}

/** Partial update: only the fields sent are changed. */
export interface PropertyUpdate {
  title?: string | null;
  address_line?: string | null;
  city?: string | null;
  neighborhood?: string | null;
  property_type?: PropertyType | null;
  listing_type?: ListingType | null;
  price?: number | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  sqft?: number | null;
  amenities?: string[] | null;
  available_from?: DateString | null;
  description?: string | null;
  image_url?: string | null;
  images?: string[] | null;
  is_active?: boolean | null;
  is_featured?: boolean | null;
}

export interface PropertyListParams {
  limit?: number;
  offset?: number;
}
