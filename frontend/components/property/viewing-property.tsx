'use client';

import { useEffect } from 'react';
import { ConnectionState } from 'livekit-client';
import { useChatBubble } from '@/components/chat-bubble/chat-bubble-context';

/** Read by the agent (backend/app/agent/viewing_context.py). */
const VIEWING_ATTRIBUTE = 'viewing_property_id';

/**
 * Tells the agent which listing this page shows, by setting an attribute on the customer's own
 * participant while a call is connected, and clearing it when the page goes away. An attribute
 * stays readable, so it doesn't matter whether the page or the agent was there first.
 */
export function ViewingProperty({ id }: { id: string }) {
  const { room, isConnected } = useChatBubble();

  useEffect(() => {
    if (!isConnected) return;
    const set = (value: string) => {
      if (room.state !== ConnectionState.Connected) return;
      room.localParticipant
        .setAttributes({ [VIEWING_ATTRIBUTE]: value })
        .catch((error: unknown) => {
          console.warn('Could not share the viewed listing with the agent:', error);
        });
    };
    set(id);
    return () => set('');
  }, [room, isConnected, id]);

  return null;
}
