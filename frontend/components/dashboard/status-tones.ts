import type { StatusTone } from '@/components/dashboard/status-pill';
import type {
  BookingChannel,
  BookingStatus,
  CallStatus,
  ConversationChannel,
  ConversationStatus,
  EmbeddingJobStatus,
  EmbeddingJobType,
  LeadStatus,
  ListingType,
  PropertyType,
  RagPageStatus,
  RagSourceStatus,
  RagSourceType,
} from '@/lib/api-client';

/** One label + tone per status, so every page shows a state the same way (see DESIGN.md). */
export interface StatusStyle {
  label: string;
  tone: StatusTone;
  pulse?: boolean;
}

export const CALL_STATUS: Record<CallStatus, StatusStyle> = {
  pending: { label: 'Pending', tone: 'neutral' },
  dispatched: { label: 'Dialling', tone: 'info', pulse: true },
  in_progress: { label: 'In progress', tone: 'info', pulse: true },
  completed: { label: 'Completed', tone: 'success' },
  missed: { label: 'Missed', tone: 'warning' },
  cancelled: { label: 'Cancelled', tone: 'muted' },
  failed: { label: 'Failed', tone: 'danger' },
};

export const BOOKING_STATUS: Record<BookingStatus, StatusStyle> = {
  proposed: { label: 'Proposed', tone: 'info' },
  confirmed: { label: 'Confirmed', tone: 'success' },
  cancelled: { label: 'Cancelled', tone: 'muted' },
};

export const BOOKING_CHANNEL: Record<BookingChannel, string> = {
  inbound_chat: 'Inbound chat',
  outbound_coldcall: 'Outbound call',
  dashboard: 'Dashboard',
};

export const LEAD_STATUS: Record<LeadStatus, StatusStyle> = {
  new: { label: 'New', tone: 'info' },
  contacted: { label: 'Contacted', tone: 'neutral' },
  qualified: { label: 'Qualified', tone: 'accent' },
  booked: { label: 'Booked', tone: 'success' },
  closed: { label: 'Closed', tone: 'muted' },
  lost: { label: 'Lost', tone: 'danger' },
};

export const RAG_SOURCE_STATUS: Record<RagSourceStatus, StatusStyle> = {
  pending: { label: 'Queued', tone: 'info', pulse: true },
  processing: { label: 'Processing', tone: 'info', pulse: true },
  ready: { label: 'Ready', tone: 'success' },
  stale: { label: 'Needs reindex', tone: 'warning' },
  failed: { label: 'Failed', tone: 'danger' },
  disabled: { label: 'Disabled', tone: 'muted' },
};

export const RAG_PAGE_STATUS: Record<RagPageStatus, StatusStyle> = {
  processing: { label: 'Processing', tone: 'info', pulse: true },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

export const RAG_SOURCE_TYPE: Record<RagSourceType, string> = {
  document: 'Document',
  link: 'Website',
  text: 'Text',
  properties: 'Property listings',
};

export const JOB_STATUS: Record<EmbeddingJobStatus, StatusStyle> = {
  pending: { label: 'Queued', tone: 'info', pulse: true },
  processing: { label: 'Running', tone: 'info', pulse: true },
  succeeded: { label: 'Succeeded', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

export const JOB_TYPE: Record<EmbeddingJobType, string> = {
  ingest: 'Embed',
  crawl: 'Crawl',
  reindex: 'Reindex',
  delete: 'Delete',
  sync_properties: 'Sync listings',
  migrate_embedding: 'Re-embed',
};

export const CONVERSATION_STATUS: Record<ConversationStatus, StatusStyle> = {
  active: { label: 'Live', tone: 'success', pulse: true },
  ended: { label: 'Ended', tone: 'muted' },
};

export const CONVERSATION_CHANNEL: Record<ConversationChannel, string> = {
  inbound_chat: 'Inbound chat',
  outbound_coldcall: 'Outbound call',
};

export const PROPERTY_TYPE: Record<PropertyType, string> = {
  apartment: 'Flat',
  studio: 'Studio',
  duplex: 'Duplex',
  commercial: 'Commercial',
  plot: 'Plot',
};

export const LISTING_TYPE: Record<ListingType, string> = {
  rent: 'For rent',
  sale: 'For sale',
};

/** Looks up a status style, falling back to the raw value for one the UI doesn't know yet. */
export function styleOf<K extends string>(
  table: Record<K, StatusStyle>,
  value: string
): StatusStyle {
  return table[value as K] ?? { label: value, tone: 'neutral' };
}
