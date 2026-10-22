import type {
  AgentConfig,
  AgentConfigUpdate,
  LlmProvider,
  ReasoningEffort,
  SttTtsProvider,
  UUID,
} from '@/lib/api-client';

/**
 * What the Chatbot form holds while it is being edited. Numbers stay strings until Save parses
 * them, so a half-typed value never jumps. Template fields are `null` when they will be reset to
 * the built-in default on save.
 */
export interface ConfigDraft {
  assistant_name: string;
  operator_name: string;
  operator_phone: string;
  operator_address: string;
  prompt_identity_rules: string;
  greeting_inbound: string | null;
  greeting_nudge: string | null;

  llm_provider: LlmProvider;
  llm_model: string;
  temperature: string;
  max_output_tokens: string;
  /** '' = the server default. */
  reasoning_effort: ReasoningEffort | '';
  /** Write-only: null keeps the saved key, '' removes it, anything else replaces it. */
  api_key: string | null;

  stt_tts_provider: SttTtsProvider;
  deepgram_tts_model: string;
  elevenlabs_voice_id: string;
  elevenlabs_tts_model: string;

  quick_reply_enabled: boolean;
  quick_fast_answer: boolean;
  quick_filler: boolean;
  /** '' = the server default. */
  quick_reply_model: string;

  rag_enabled: boolean;
  rag_top_k: number;
  rag_similarity_threshold: number;
  chunk_size: string;
  chunk_overlap: string;
  rag_source_ids: UUID[];
}

export type DraftKey = keyof ConfigDraft;

/** Which tab each field is on, so a refused value can switch to it. */
export const FIELD_TAB: Record<DraftKey, ChatbotTab> = {
  assistant_name: 'agent',
  operator_name: 'agent',
  operator_phone: 'agent',
  operator_address: 'agent',
  prompt_identity_rules: 'agent',
  greeting_inbound: 'agent',
  greeting_nudge: 'agent',
  llm_provider: 'model',
  llm_model: 'model',
  temperature: 'model',
  max_output_tokens: 'model',
  reasoning_effort: 'model',
  api_key: 'model',
  stt_tts_provider: 'model',
  deepgram_tts_model: 'model',
  elevenlabs_voice_id: 'model',
  elevenlabs_tts_model: 'model',
  quick_reply_enabled: 'model',
  quick_fast_answer: 'model',
  quick_filler: 'model',
  quick_reply_model: 'model',
  rag_enabled: 'knowledge',
  rag_top_k: 'knowledge',
  rag_similarity_threshold: 'knowledge',
  chunk_size: 'knowledge',
  chunk_overlap: 'knowledge',
  rag_source_ids: 'knowledge',
};

export type ChatbotTab = 'agent' | 'model' | 'knowledge';
export const CHATBOT_TABS: ChatbotTab[] = ['agent', 'model', 'knowledge'];

export function draftFrom(config: AgentConfig): ConfigDraft {
  return {
    assistant_name: config.assistant_name,
    operator_name: config.operator_name,
    operator_phone: config.operator_phone,
    operator_address: config.operator_address,
    prompt_identity_rules: config.prompt_identity_rules,
    greeting_inbound: config.greeting_inbound,
    greeting_nudge: config.greeting_nudge,
    llm_provider: config.llm_provider,
    llm_model: config.llm_model,
    temperature: config.temperature === null ? '' : String(config.temperature),
    max_output_tokens: config.max_output_tokens === null ? '' : String(config.max_output_tokens),
    reasoning_effort: config.reasoning_effort ?? '',
    api_key: null,
    stt_tts_provider: config.stt_tts_provider,
    deepgram_tts_model: config.deepgram_tts_model,
    elevenlabs_voice_id: config.elevenlabs_voice_id,
    elevenlabs_tts_model: config.elevenlabs_tts_model,
    quick_reply_enabled: config.quick_reply_enabled,
    quick_fast_answer: config.quick_fast_answer,
    quick_filler: config.quick_filler,
    quick_reply_model: config.quick_reply_model ?? '',
    rag_enabled: config.rag_enabled,
    rag_top_k: config.rag_top_k,
    rag_similarity_threshold: config.rag_similarity_threshold,
    chunk_size: String(config.chunk_size),
    chunk_overlap: String(config.chunk_overlap),
    rag_source_ids: [...config.rag_source_ids],
  };
}

function same(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v) => b.includes(v));
  }
  return a === b;
}

/** The fields whose draft value differs from what is saved. */
export function changedKeys(draft: ConfigDraft, saved: AgentConfig): DraftKey[] {
  const base = draftFrom(saved);
  return (Object.keys(draft) as DraftKey[]).filter((key) => !same(draft[key], base[key]));
}

/** Takes a newer saved config (a poll, a prompt reset) without losing fields being edited:
 * a field still equal to the old saved value follows the new one. */
export function rebase(draft: ConfigDraft, oldSaved: AgentConfig, newSaved: AgentConfig) {
  const before = draftFrom(oldSaved);
  const after = draftFrom(newSaved);
  const next = { ...draft };
  for (const key of Object.keys(draft) as DraftKey[]) {
    if (same(draft[key], before[key])) {
      (next as Record<DraftKey, unknown>)[key] = after[key];
    }
  }
  return next;
}

export type FieldErrors = Partial<Record<DraftKey, string>>;

function wholeIn(text: string, min: number, max: number): number | null {
  if (!/^\s*\d+\s*$/.test(text)) return null;
  const value = Number.parseInt(text, 10);
  return value >= min && value <= max ? value : null;
}

/** The PATCH body for the changed fields, or the per-field reasons it can't be sent. */
export function buildUpdate(
  draft: ConfigDraft,
  saved: AgentConfig
): { payload: AgentConfigUpdate } | { errors: FieldErrors } {
  const payload: AgentConfigUpdate = {};
  const errors: FieldErrors = {};

  for (const key of changedKeys(draft, saved)) {
    switch (key) {
      case 'assistant_name':
      case 'operator_name': {
        const value = draft[key].trim();
        if (!value) errors[key] = 'Enter a name, or put back the saved one.';
        else payload[key] = value;
        break;
      }
      case 'operator_phone':
      case 'operator_address':
        // Blank = back to the default.
        payload[key] = draft[key].trim() || null;
        break;
      case 'prompt_identity_rules':
        if (!draft.prompt_identity_rules.trim()) {
          errors[key] = 'The instructions can’t be empty. Use “Reset to default” instead.';
        } else payload[key] = draft.prompt_identity_rules;
        break;
      case 'greeting_inbound':
      case 'greeting_nudge':
        // null or blank = back to the default.
        payload[key] = draft[key]?.trim() ? draft[key] : null;
        break;
      case 'llm_model':
        payload.llm_model = draft.llm_model.trim() || null;
        break;
      case 'temperature': {
        const text = draft.temperature.trim();
        if (!text) payload.temperature = null;
        else {
          const value = Number(text);
          if (!Number.isFinite(value) || value < 0 || value > 2) {
            errors.temperature = 'Use a number from 0 to 2, or leave it blank.';
          } else payload.temperature = value;
        }
        break;
      }
      case 'max_output_tokens': {
        const text = draft.max_output_tokens.trim();
        if (!text) payload.max_output_tokens = null;
        else {
          const value = wholeIn(text, 1, 32768);
          if (value === null) errors.max_output_tokens = 'Use a whole number from 1 to 32,768.';
          else payload.max_output_tokens = value;
        }
        break;
      }
      case 'reasoning_effort':
        payload.reasoning_effort = draft.reasoning_effort || null;
        break;
      case 'quick_reply_model':
        payload.quick_reply_model = draft.quick_reply_model || null;
        break;
      case 'api_key':
        payload.api_key = draft.api_key;
        break;
      case 'chunk_size': {
        const value = wholeIn(draft.chunk_size, 64, 4096);
        if (value === null) errors.chunk_size = 'Use a whole number from 64 to 4,096.';
        else payload.chunk_size = value;
        break;
      }
      case 'chunk_overlap': {
        const value = wholeIn(draft.chunk_overlap, 0, 1024);
        if (value === null) errors.chunk_overlap = 'Use a whole number from 0 to 1,024.';
        else payload.chunk_overlap = value;
        break;
      }
      case 'deepgram_tts_model':
      case 'elevenlabs_voice_id':
      case 'elevenlabs_tts_model':
        payload[key] = draft[key].trim() || null;
        break;
      default:
        (payload as Record<string, unknown>)[key] = draft[key];
    }
  }

  const size = wholeIn(draft.chunk_size, 64, 4096);
  const overlap = wholeIn(draft.chunk_overlap, 0, 1024);
  if (size !== null && overlap !== null && overlap >= size && !errors.chunk_overlap) {
    errors.chunk_overlap = 'The overlap must be smaller than the chunk size.';
  }

  return Object.keys(errors).length ? { errors } : { payload };
}

/** Maps a server refusal ("greeting_inbound: Unknown placeholder {x}", or several joined by
 * "; ") onto the fields it names. Unmatched text comes back as `rest`. */
export function parseServerErrors(message: string): { errors: FieldErrors; rest: string | null } {
  const errors: FieldErrors = {};
  const rest: string[] = [];
  for (const part of message.split('; ')) {
    const match = /^([a-z_]+)(?:\.\d+)?: ([\s\S]+)$/.exec(part.trim());
    if (match && match[1] in FIELD_TAB) errors[match[1] as DraftKey] = match[2];
    else if (part.trim()) rest.push(part.trim());
  }
  return { errors, rest: rest.length ? rest.join(' ') : null };
}
