'use client';

import { useEffect, useRef } from 'react';
import { useSessionContext } from '@livekit/components-react';
import { useAgentAttribute } from '@/lib/livekit-text-streams';
import type { PortalMe } from '@/lib/types/portal';

// Must match ACCOUNT_ATTRIBUTE in backend/app/agent/account_link.py: the session's subscriber
// id, "" for a guest.
const ACCOUNT_ATTRIBUTE = 'account';

/**
 * Keeps the assistant session's account in step with the login. A guest who logs in mid-chat
 * gets the same session linked to their account (`/api/assistant/link`), so the conversation
 * carries on. A session that belongs to a customer is ended once that customer logs out or
 * another one logs in: it never moves between accounts. `me` is undefined while still loading.
 */
export function AccountLink({ me }: { me: PortalMe | null | undefined }) {
  const session = useSessionContext();
  const account = useAgentAttribute(ACCOUNT_ATTRIBUTE);
  const linkedRoomRef = useRef<string | null>(null);

  useEffect(() => {
    if (!session.isConnected || account === undefined || me === undefined) return;
    const mine = me?.subscriber_id ?? null;
    const theirs = account || null;
    if (theirs === mine) return;

    if (theirs === null && mine !== null) {
      const room = session.room;
      if (linkedRoomRef.current === room.name) return;
      linkedRoomRef.current = room.name;
      void fetch('/api/assistant/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_name: room.name, identity: room.localParticipant.identity }),
      }).then(
        (res) => {
          if (!res.ok) console.warn('The assistant session was not linked:', res.status);
        },
        (error: unknown) => console.warn('The assistant session was not linked:', error)
      );
      return;
    }

    // Logged out, or now a different customer: this session isn't theirs any more.
    void session.end();
  }, [session, account, me]);

  return null;
}
