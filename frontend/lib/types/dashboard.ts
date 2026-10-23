import type { DateString } from './common';

export interface DashboardSummary {
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
