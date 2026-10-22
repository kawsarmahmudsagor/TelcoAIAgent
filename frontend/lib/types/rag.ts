import type { EmbeddingMigrationStatus } from './agent-config';
import type { DateTimeString, UUID } from './common';

/** The backend serializes these as plain strings; these are the values it writes. */
export type RagSourceType = 'document' | 'link' | 'text' | 'properties';

/** `stale`: embedded with chunk settings that have since changed; still searchable. */
export type RagSourceStatus = 'pending' | 'processing' | 'ready' | 'stale' | 'failed' | 'disabled';

export type RagPageStatus = 'processing' | 'ready' | 'failed';

export type EmbeddingJobType =
  | 'ingest'
  | 'crawl'
  | 'reindex'
  | 'delete'
  | 'sync_properties'
  | 'migrate_embedding';

export type EmbeddingJobStatus = 'pending' | 'processing' | 'succeeded' | 'failed';

export interface EmbeddingJob {
  id: UUID;
  rag_source_id: UUID | null;
  job_type: EmbeddingJobType;
  status: EmbeddingJobStatus;
  attempts: number;
  payload: Record<string, unknown>;
  error: string | null;
  stats: Record<string, unknown>;
  created_at: DateTimeString;
  started_at: DateTimeString | null;
  finished_at: DateTimeString | null;
}

export interface RagSource {
  id: UUID;
  name: string;
  source_type: RagSourceType;
  status: RagSourceStatus;
  source_url: string | null;
  filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  embedding_model: string;
  chunk_count: number;
  config: Record<string, unknown>;
  error: string | null;
  last_indexed_at: DateTimeString | null;
  created_at: DateTimeString;
  updated_at: DateTimeString;
  /** The newest job, for progress display and retry. */
  latest_job: EmbeddingJob | null;
}

export interface RagSourcePage {
  id: UUID;
  url: string;
  title: string | null;
  depth: number;
  status: RagPageStatus;
  chunk_count: number;
  error: string | null;
}

export interface RagSourceDetail extends RagSource {
  /** The text of a text source. */
  content: string | null;
  pages: RagSourcePage[];
  /** Up to the 10 newest jobs. */
  jobs: EmbeddingJob[];
}

export interface RagSourceList {
  items: RagSource[];
  total: number;
}

export interface RagSourceListParams {
  source_type?: RagSourceType;
  status?: RagSourceStatus;
  /** 1..500, default 100 */
  limit?: number;
  offset?: number;
}

export interface CreateSourceResponse {
  source: RagSource;
  job: EmbeddingJob;
}

export interface LinkSourceCreate {
  url: string;
  name?: string | null;
  /** 0..3 */
  max_depth?: number | null;
  /** 1..100 */
  max_pages?: number | null;
  /** Empty = the start URL's host (and its subdomains). Max 20. */
  allowed_domains?: string[];
}

export interface TextSourceCreate {
  name: string;
  text: string;
}

export interface ReindexAllResponse {
  queued: number;
}

export interface EmbeddingJobListParams {
  source_id?: UUID;
  status?: EmbeddingJobStatus;
  /** 1..200, default 50 */
  limit?: number;
}

export interface RagSearchRequest {
  query: string;
  /** Defaults to the agent config's top-k (1..20). */
  top_k?: number | null;
  /** Defaults to the agent config's threshold (0..1). */
  threshold?: number | null;
  /** Defaults to the agent config's source scope. */
  source_ids?: UUID[] | null;
}

export interface RagSearchHit {
  text: string;
  score: number | null;
  rag_source_id: string | null;
  rag_source_name: string | null;
  metadata: Record<string, unknown>;
}

export interface RagSearchResponse {
  embedding_model: string;
  top_k: number;
  threshold: number;
  results: RagSearchHit[];
}

export interface RagSourceCounts {
  total: number;
  pending: number;
  processing: number;
  ready: number;
  stale: number;
  failed: number;
  disabled: number;
}

export interface RagStatus {
  rag_enabled: boolean;
  /** False = no OpenRouter key, so nothing can be embedded or searched. */
  embedding_ready: boolean;
  chroma_reachable: boolean;
  embedding_model: string;
  sources: RagSourceCounts;
  total_chunks: number;
  jobs_pending: number;
  jobs_processing: number;
  jobs_failed: number;
  embedding_migration_status: EmbeddingMigrationStatus | null;
  embedding_migration_target: string | null;
  embedding_migration_error: string | null;
}
