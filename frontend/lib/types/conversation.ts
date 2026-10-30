import type { ReplyLanguage } from '@/lib/reply-language';
import type { DateTimeString, UUID } from './common';

/** Serialized as a plain string by the backend; these are the values it writes. */
export type ConversationChannel = 'inbound_chat';

export type ConversationStatus = 'active' | 'ended';

export type MessageRole = 'user' | 'assistant' | 'tool';

export interface Conversation {
  id: UUID;
  channel: ConversationChannel;
  room_name: string | null;
  subscriber_id: UUID | null;
  is_phone_call: boolean;
  status: ConversationStatus;
  message_count: number;
  started_at: DateTimeString;
  ended_at: DateTimeString | null;
  /** The language the customer picked for the chat; null for calls and older chats. */
  reply_language: ReplyLanguage | null;
}

export interface ConversationListItem extends Conversation {
  subscriber_name: string | null;
  /** First thing the customer said, trimmed. */
  preview: string | null;
}

export interface ConversationPage {
  items: ConversationListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ConversationMessage {
  id: UUID;
  seq: number;
  role: MessageRole;
  text: string | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  created_at: DateTimeString;
}

export interface ConversationDetail extends Conversation {
  subscriber_name: string | null;
  messages: ConversationMessage[];
}

export interface ConversationListParams {
  channel?: ConversationChannel;
  status?: ConversationStatus;
  subscriber_id?: UUID;
  /** 1..200, default 50 */
  limit?: number;
  offset?: number;
}

export interface BulkDeleteRequest {
  /** 1..500 ids */
  ids: UUID[];
}

export interface BulkDeleteResult {
  deleted: number;
}

/** The chat bubble's history: one of this browser's earlier conversations (public API). */
export interface VisitorConversationSummary {
  id: UUID;
  started_at: DateTimeString;
  ended_at: DateTimeString | null;
  status: ConversationStatus;
  /** First thing the customer said, trimmed. */
  preview: string | null;
  /** Customer + agent messages (tool rows aren't shown). */
  message_count: number;
  /** The language the customer picked for this chat; null for chats from before the pick. */
  reply_language: ReplyLanguage | null;
}

export interface VisitorConversationPage {
  items: VisitorConversationSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface VisitorConversationMessage {
  seq: number;
  role: Exclude<MessageRole, 'tool'>;
  text: string | null;
  created_at: DateTimeString;
}

export interface VisitorConversationDetail {
  id: UUID;
  started_at: DateTimeString;
  ended_at: DateTimeString | null;
  status: ConversationStatus;
  /** The language the customer picked for this chat; null for chats from before the pick. */
  reply_language: ReplyLanguage | null;
  messages: VisitorConversationMessage[];
}
