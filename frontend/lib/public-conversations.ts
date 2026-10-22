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
