/**
 * The language the customer picks when a chat opens: the agent replies only in it, whatever
 * language they write or speak (backend/app/agent/reply_language.py). Fixed for the chat.
 */
export type ReplyLanguage = 'en' | 'bn';

/** The value if it is exactly 'en' or 'bn'; otherwise undefined. */
export function replyLanguageOrUndefined(value: unknown): ReplyLanguage | undefined {
  return value === 'en' || value === 'bn' ? value : undefined;
}
