import { replyLanguageOrUndefined } from '@/lib/reply-language';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The value, lower-cased, if it is a well-formed UUID; otherwise undefined. */
function uuidOrUndefined(value: unknown): string | undefined {
  return typeof value === 'string' && UUID_PATTERN.test(value) ? value.toLowerCase() : undefined;
}

/**
 * The job metadata for an inbound chat dispatch of the telco agent (read by
 * backend/app/agent/session_context.py). `subscriberId` must come from a server-verified
 * `portal_session`, never from the browser; `visitorId`, `nudgeId` and `resumeConversationId` are
 * browser-supplied, so they are kept only when they are UUIDs. `textStart` (the attribute "1")
 * marks a session opened by a typed message: the agent answers it without a greeting.
 * `resumeConversationId` is an earlier chat to carry on; the agent reopens it only if it belongs
 * to this visitor or subscriber. `replyLanguage` ('en' or 'bn', anything else dropped) is the
 * language the customer picked for the chat: every reply is in it.
 */
export function buildDispatchMetadata(
  subscriberId: string | null,
  extras: {
    visitorId?: string;
    nudgeId?: string;
    textStart?: string;
    resumeConversationId?: string;
    replyLanguage?: unknown;
  }
): string {
  const replyLanguage = replyLanguageOrUndefined(extras.replyLanguage);
  const visitorId = uuidOrUndefined(extras.visitorId);
  const nudgeId = uuidOrUndefined(extras.nudgeId);
  const resumeConversationId = uuidOrUndefined(extras.resumeConversationId);
  return JSON.stringify({
    channel: 'inbound_chat',
    ...(subscriberId ? { subscriber_id: subscriberId } : {}),
    ...(visitorId ? { visitor_id: visitorId } : {}),
    ...(nudgeId ? { nudge_id: nudgeId } : {}),
    ...(extras.textStart === '1' ? { text_start: true } : {}),
    ...(resumeConversationId ? { resume_conversation_id: resumeConversationId } : {}),
    ...(replyLanguage ? { reply_language: replyLanguage } : {}),
  });
}
