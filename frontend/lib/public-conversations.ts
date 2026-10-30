import type { Participant } from 'livekit-client';
import type { ReceivedMessage } from '@livekit/components-react';
import type { ReplyLanguage } from '@/lib/reply-language';
import type { VisitorConversationDetail, VisitorConversationPage } from '@/lib/types';

// Same-origin `/backend`, proxied to FastAPI (see lib/api-client.ts).
const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL || '/backend';

async function visitorFetch<T>(path: string, visitorId: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${FASTAPI_URL}${path}`, {
    // The visitor id is a secret: a header, never the query string.
    headers: { 'X-Visitor-Id': visitorId },
    cache: 'no-store',
    signal,
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return (await res.json()) as T;
}

/** A page of this browser's earlier chats, newest first. `excludeRoom` drops the live one. */
export function listVisitorConversations(
  visitorId: string,
  { limit, offset, excludeRoom }: { limit: number; offset: number; excludeRoom?: string },
  signal?: AbortSignal
): Promise<VisitorConversationPage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (excludeRoom) params.set('exclude_room', excludeRoom);
  return visitorFetch(`/api/public/conversations?${params}`, visitorId, signal);
}

/** One earlier chat's messages (customer + agent only). */
export function getVisitorConversation(
  visitorId: string,
  conversationId: string,
  signal?: AbortSignal
): Promise<VisitorConversationDetail> {
  return visitorFetch(
    `/api/public/conversations/${encodeURIComponent(conversationId)}`,
    visitorId,
    signal
  );
}

/** An ended chat as a Word file (raw response: 409 while live, 502 when translation fails). */
export function exportVisitorConversation(
  visitorId: string,
  conversationId: string,
  lang: ReplyLanguage
): Promise<Response> {
  return fetch(
    `${FASTAPI_URL}/api/public/conversations/${encodeURIComponent(conversationId)}/export?lang=${lang}`,
    // The portal session cookie lets a signed-in customer export their chats from any browser.
    { headers: { 'X-Visitor-Id': visitorId }, cache: 'no-store', credentials: 'include' }
  );
}

/**
 * A stored chat's messages in the live transcript's shape, so the panel shows them the same way.
 * Only `from.isLocal` is read off the sender (customer vs agent), so a stand-in is enough.
 */
export function toReceivedMessages(detail: VisitorConversationDetail): ReceivedMessage[] {
  const customer = { isLocal: true } as Participant;
  return detail.messages
    .filter((m) => m.text?.trim())
    .map(
      (m) =>
        ({
          type: 'chatMessage',
          id: `history-${detail.id}-${m.seq}`,
          timestamp: new Date(m.created_at).getTime(),
          message: m.text ?? '',
          from: m.role === 'user' ? customer : undefined,
        }) as ReceivedMessage
    );
}
