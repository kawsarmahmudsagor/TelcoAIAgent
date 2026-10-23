import type { StatusTone } from '@/components/dashboard/status-pill';
import type {
  ConversationChannel,
  ConversationStatus,
  EmbeddingJobStatus,
  EmbeddingJobType,
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
  migrate_embedding: 'Re-embed',
};

export const CONVERSATION_STATUS: Record<ConversationStatus, StatusStyle> = {
  active: { label: 'Live', tone: 'success', pulse: true },
  ended: { label: 'Ended', tone: 'muted' },
};

export const CONVERSATION_CHANNEL: Record<ConversationChannel, string> = {
  inbound_chat: 'Inbound chat',
};

/** Looks up a status style, falling back to the raw value for one the UI doesn't know yet. */
export function styleOf<K extends string>(
  table: Record<K, StatusStyle>,
  value: string
): StatusStyle {
  return table[value as K] ?? { label: value, tone: 'neutral' };
}
