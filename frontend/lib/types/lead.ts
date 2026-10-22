import type { DateString, DateTimeString, UUID } from './common';

export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'booked' | 'closed' | 'lost';

export type RentOrBuy = 'rent' | 'buy' | 'undecided';

/** A lead (backend `ClientOut`). */
export interface Client {
  id: UUID;
  full_name: string;
  phone: string | null;
  email: string | null;
  lead_source: string | null;
  lead_status: LeadStatus;
  budget_min: number | null;
  budget_max: number | null;
  preferred_location: string | null;
  preferred_property_type: string | null;
  bedrooms_wanted: number | null;
  bathrooms_wanted: number | null;
  move_in_date: DateString | null;
  rent_or_buy: RentOrBuy;
  notes: string | null;
  created_at: DateTimeString;
  updated_at: DateTimeString;
}

export interface ClientCreate {
  full_name: string;
  phone?: string | null;
  email?: string | null;
  lead_source?: string | null;
  lead_status?: LeadStatus;
  budget_min?: number | null;
  budget_max?: number | null;
  preferred_location?: string | null;
  preferred_property_type?: string | null;
  bedrooms_wanted?: number | null;
  bathrooms_wanted?: number | null;
  move_in_date?: DateString | null;
  rent_or_buy?: RentOrBuy;
  notes?: string | null;
}

export interface ClientUpdate {
  lead_status?: LeadStatus | null;
  notes?: string | null;
}

export interface LeadListParams {
  lead_status?: LeadStatus;
  limit?: number;
  offset?: number;
}

/** Result of `POST /api/import/clients` (.xlsx upload). */
export interface ImportClientsResult {
  imported: number;
  skipped: number;
  errors: string[];
}
