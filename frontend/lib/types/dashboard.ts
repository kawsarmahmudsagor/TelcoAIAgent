import type { BookingChannel, BookingStatus } from './booking';
import type { DateString, DateTimeString, UUID } from './common';

export interface DashboardSummary {
  total_leads: number;
  pending_calls_today: number;
  bookings_this_week: number;
  active_listings: number;
  conversations_today: number;
  /** Knowledge base: searchable (ready/stale) sources out of all sources. */
  kb_sources_ready: number;
  kb_sources_total: number;
}

export type SeriesRange = '7d' | '30d' | '90d';

export interface SeriesPoint {
  /** Local calendar day in the agency timezone. */
  date: DateString;
  count: number;
}

export interface ConversationSeries {
  range: SeriesRange;
  /** IANA timezone name of the agency. */
  timezone: string;
  total: number;
  /** Zero-filled, oldest first, ending today. */
  points: SeriesPoint[];
}

export interface RecentBooking {
  id: UUID;
  client_id: UUID;
  client_name: string | null;
  property_id: UUID | null;
  property_title: string | null;
  channel: BookingChannel;
  status: BookingStatus;
  proposed_datetime: DateTimeString;
  created_at: DateTimeString;
}
