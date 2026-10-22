import type { DateString, DateTimeString, UUID } from './common';
import type { ListingType } from './property';

export type OfferType =
  // Price discounts.
  | 'percent_discount'
  | 'flat_discount'
  | 'single_payment_discount'
  // Payment and fee perks.
  | 'installment_plan'
  | 'reduced_booking_money'
  | 'fee_waiver'
  | 'free_parking';

/** A linked listing as the dashboard shows it, including ones no longer on sale. */
export interface OfferProperty {
  id: UUID;
  title: string;
  city: string;
  neighborhood: string | null;
  listing_type: ListingType;
  is_active: boolean;
}

export interface Offer {
  id: UUID;
  title: string;
  description: string | null;
  terms: string | null;
  offer_type: OfferType;
  discount_percent: number | null;
  /** Taka. */
  discount_amount: number | null;
  starts_on: DateString | null;
  ends_on: DateString | null;
  is_active: boolean;
  applies_to_all_sale: boolean;
  property_ids: UUID[];
  properties: OfferProperty[];
  created_at: DateTimeString;
  updated_at: DateTimeString;
}

export interface OfferCreate {
  title: string;
  description?: string | null;
  terms?: string | null;
  offer_type: OfferType;
  discount_percent?: number | null;
  discount_amount?: number | null;
  starts_on?: DateString | null;
  ends_on?: DateString | null;
  is_active?: boolean;
  /** When true the backend clears property_ids. */
  applies_to_all_sale?: boolean;
  property_ids?: UUID[];
}

/** Partial update, merged onto the offer and validated as a whole. */
export type OfferUpdate = Partial<OfferCreate>;

/** An offer as a listing's badge shows it (`PublicListing.offers`, chat cards). */
export interface ListingOffer {
  id: UUID;
  title: string;
  offer_type: OfferType;
  discount_percent: number | null;
  discount_amount: number | null;
  ends_on: DateString | null;
}

export interface OfferListingSummary {
  id: UUID;
  title: string;
  city: string;
  neighborhood: string | null;
  price: number;
  image_url: string | null;
}

/** A live offer on the public site (`GET /api/public/offers`). */
export interface PublicOffer {
  id: UUID;
  title: string;
  description: string | null;
  terms: string | null;
  offer_type: OfferType;
  discount_percent: number | null;
  discount_amount: number | null;
  starts_on: DateString | null;
  ends_on: DateString | null;
  applies_to_all_sale: boolean;
  /** Up to 6 active sale listings; empty for an all-sale offer. */
  listings: OfferListingSummary[];
}
