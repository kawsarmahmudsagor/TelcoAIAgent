import type { DateTimeString, UUID } from './common';

export type LlmProvider = 'openrouter' | 'gemini';

/** How long an OpenRouter model may reason before answering. Lower = faster replies. */
export type ReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high';

/** Speech-to-text + text-to-speech vendor for voice calls. `openrouter` = ElevenLabs models
 * served through OpenRouter. */
export type SttTtsProvider = 'elevenlabs' | 'openrouter' | 'deepgram';

export type PreviewLanguage = 'en' | 'bn';

export type EmbeddingMigrationStatus = 'running' | 'succeeded' | 'failed';

/** Effective values (saved value, else the env/code default) plus `*_is_default` flags. */
export interface AgentConfig {
  assistant_name: string;
  operator_name: string;
  /** Where the agent sends customers for details it doesn't have. */
  operator_phone: string;
  operator_address: string;
  prompt_identity_rules: string;
  prompt_is_default: boolean;
  greeting_inbound: string;
  greeting_inbound_is_default: boolean;
  greeting_nudge: string;
  greeting_nudge_is_default: boolean;

  llm_provider: LlmProvider;
  llm_model: string;
  temperature: number | null;
  max_output_tokens: number | null;
  /** OpenRouter only. The saved value; null = the server default below. */
  reasoning_effort: ReasoningEffort | null;
  reasoning_effort_default: ReasoningEffort;
  /** The key itself is never returned. */
  has_api_key: boolean;
  /** False when SETTINGS_ENCRYPTION_KEY is unset: saving a key returns 400. */
  encryption_available: boolean;

  stt_tts_provider: SttTtsProvider;
  deepgram_tts_model: string;
  elevenlabs_voice_id: string;
  /** In stt_tts_provider's id format; unused with deepgram. */
  elevenlabs_tts_model: string;
  /** Voice provider 'elevenlabs' only: scribe_v2 (whole turns) or scribe_v2_realtime. */
  elevenlabs_stt_model: string;
  /** 'auto' (Bangla or English, detected per turn), 'bn' or 'en'. */
  elevenlabs_stt_language: string;

  /** Customers and guests hear the agent's replies; off, they read them (and can still speak). */
  voice_replies_enabled: boolean;
  /** Quick replies on gated voice calls: a small model answers turns that need no lookup
   * (quick_fast_answer) and speaks a short line while a lookup runs (quick_filler). */
  quick_reply_enabled: boolean;
  quick_fast_answer: boolean;
  quick_filler: boolean;
  /** The saved model; null = the server default below. */
  quick_reply_model: string | null;
  quick_reply_model_default: string;

  rag_enabled: boolean;
  rag_top_k: number;
  rag_similarity_threshold: number;
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  embedding_migration_status: EmbeddingMigrationStatus | null;
  embedding_migration_target: string | null;
  embedding_migration_error: string | null;
  /** Sources the agent may search; empty = all ready sources. */
  rag_source_ids: UUID[];
  /** False = no OpenRouter key for embeddings, so the knowledge base can't work. */
  embedding_ready: boolean;

  updated_at: DateTimeString | null;
}

/**
 * Only the fields sent are changed; null (or a blank string) resets a field to its default.
 * `api_key` is write-only: omitted/null keeps the saved key, "" clears it.
 * Null is ignored for rag_enabled, rag_top_k, rag_similarity_threshold, chunk_size, chunk_overlap.
 */
export interface AgentConfigUpdate {
  assistant_name?: string | null;
  operator_name?: string | null;
  operator_phone?: string | null;
  operator_address?: string | null;
  prompt_identity_rules?: string | null;
  greeting_inbound?: string | null;
  greeting_nudge?: string | null;

  llm_provider?: LlmProvider | null;
  llm_model?: string | null;
  /** 0..2 */
  temperature?: number | null;
  /** 1..32768 */
  max_output_tokens?: number | null;
  /** OpenRouter only. Reset to the default when llm_provider changes. */
  reasoning_effort?: ReasoningEffort | null;
  api_key?: string | null;

  stt_tts_provider?: SttTtsProvider | null;
  deepgram_tts_model?: string | null;
  elevenlabs_voice_id?: string | null;
  /** Reset to the default when stt_tts_provider changes, unless sent with it. */
  elevenlabs_tts_model?: string | null;
  /** Null or blank: the server default model; 'auto' or null: detect the language. */
  elevenlabs_stt_model?: string | null;
  elevenlabs_stt_language?: string | null;

  /** Null is ignored. */
  voice_replies_enabled?: boolean | null;
  /** Null is ignored for the three switches. */
  quick_reply_enabled?: boolean | null;
  quick_fast_answer?: boolean | null;
  quick_filler?: boolean | null;
  /** One of the `quick_reply_models` options; null = the server default. */
  quick_reply_model?: string | null;

  rag_enabled?: boolean | null;
  /** 1..20 */
  rag_top_k?: number | null;
  /** 0..1 */
  rag_similarity_threshold?: number | null;
  /** 64..4096 */
  chunk_size?: number | null;
  /** 0..1024, must be smaller than chunk_size. */
  chunk_overlap?: number | null;
  /** Replaces the source scope; [] = all sources. */
  rag_source_ids?: UUID[] | null;
}

export interface ModelOption {
  id: string;
  label: string;
}

/** Picker suggestions. LLM model ids are free text. */
export interface AgentConfigOptions {
  llm_providers: LlmProvider[];
  /** Keyed by LlmProvider. */
  llm_models: Record<string, ModelOption[]>;
  embedding_models: ModelOption[];
  stt_tts_providers: SttTtsProvider[];
  deepgram_tts_voices: ModelOption[];
  elevenlabs_voices: ModelOption[];
  /** Keyed by provider ('elevenlabs', 'openrouter'): the ids differ between them. */
  elevenlabs_tts_models: Record<string, ModelOption[]>;
  /** The only STT models and languages voice provider 'elevenlabs' accepts. */
  elevenlabs_stt_models: ModelOption[];
  elevenlabs_stt_languages: ModelOption[];
  /** The only models quick replies accept. */
  quick_reply_models: ModelOption[];
  /** Allowed `{placeholders}` per template field. */
  placeholders: Record<string, string[]>;
}

/** The unsaved voice choice to audition. `voice` is the ElevenLabs voice id, or the Deepgram
 * Aura model. `model` empty = the provider's default. */
export interface VoicePreviewRequest {
  stt_tts_provider: SttTtsProvider;
  voice: string;
  model?: string | null;
  language: PreviewLanguage;
}

export interface MigrateEmbeddingRequest {
  embedding_model: string;
}
