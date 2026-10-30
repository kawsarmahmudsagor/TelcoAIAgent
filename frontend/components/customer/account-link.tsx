'use client';

import { useEffect, useRef } from 'react';
import { useSessionContext } from '@livekit/components-react';
import { useAssistant } from '@/components/portal/assistant/assistant-provider';
import { useAgentAttribute } from '@/lib/livekit-text-streams';
import type { PortalMe } from '@/lib/types/portal';

// Must match ACCOUNT_ATTRIBUTE in backend/app/agent/account_link.py: the session's subscriber
// id, "" for a guest.
const ACCOUNT_ATTRIBUTE = 'account';

/**
 * Keeps the assistant session's account in step with the login. A session never moves between
 * accounts: a guest who logs in mid-chat gets a new conversation (the guest's is ended and
 * cleared), and a customer's session is ended once they log out or another one logs in. `me` is
 * undefined while still loading.
 */
export function AccountLink({ me }: { me: PortalMe | null | undefined }) {
  const session = useSessionContext();
  const account = useAgentAttribute(ACCOUNT_ATTRIBUTE);
  const { startOverForLogin } = useAssistant();
  const signedInRef = useRef<string | null | undefined>(undefined);

  // A guest just logged in (not a page load that finds a customer already signed in).
  useEffect(() => {
    if (me === undefined) return;
    const mine = me?.subscriber_id ?? null;
    const before = signedInRef.current;
    signedInRef.current = mine;
    if (before === null && mine !== null) startOverForLogin();
  }, [me, startOverForLogin]);

  // Logged out, or now a different customer: this customer's session isn't theirs any more.
  useEffect(() => {
    if (!session.isConnected || !account || me === undefined) return;
    if (account !== (me?.subscriber_id ?? null)) void session.end();
  }, [session, account, me]);

  return null;
}
