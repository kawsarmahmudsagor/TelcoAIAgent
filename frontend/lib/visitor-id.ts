'use client';

import { useMemo, useSyncExternalStore } from 'react';

/**
 * This browser's anonymous visitor id: a random UUID made once and kept in localStorage. The
 * token route passes it to the agent, which stores it on the conversation row, and the chat
 * bubble's history lists conversations by it. It's a bearer-like secret -- whoever has it can
 * read those transcripts -- so it's only ever sent to our own API (X-Visitor-Id header) and the
 * token route.
 */
const STORAGE_KEY = 'realestate.visitor-id';
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// When storage is unavailable (private window, blocked site data), one id per page load: the
// history then only covers this tab's own conversations, but nothing breaks.
let memoryId: string | null = null;

export function isVisitorId(value: unknown): value is string {
  return typeof value === 'string' && UUID_PATTERN.test(value);
}

function randomUuid(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  // crypto.randomUUID needs a secure context (plain-http LAN access lacks it).
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** Reads (or makes and stores) the visitor id. Browser only. */
export function getOrCreateVisitorId(): string {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isVisitorId(stored)) return stored.toLowerCase();
  } catch {
    // storage unavailable -- fall through to the in-memory id
  }
  if (memoryId) return memoryId;
  const id = randomUuid().toLowerCase();
  memoryId = id;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // keep the in-memory id
  }
  return id;
}

const subscribe = () => () => {};
const serverSnapshot = () => null;

/** The visitor id in the browser (null during SSR and hydration). */
export function useVisitorId(): string | null {
  return useSyncExternalStore(subscribe, getOrCreateVisitorId, serverSnapshot);
}

/**
 * useSession's token fetch options for a new inbound chat: the agent name, plus the visitor id
 * as a participant attribute -- the token route moves it into the agent's dispatch metadata, so
 * the conversation row records it. Memoized: useSession compares the attributes by reference
 * and refetches the token when they change.
 */
export function useVisitorSessionOptions(agentName: string | undefined, visitorId: string | null) {
  return useMemo(
    () => ({
      ...(agentName ? { agentName } : {}),
      ...(visitorId ? { participantAttributes: { visitor_id: visitorId } } : {}),
    }),
    [agentName, visitorId]
  );
}
