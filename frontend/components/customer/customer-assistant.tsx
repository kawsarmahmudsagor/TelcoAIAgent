'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { AccountLink } from '@/components/customer/account-link';
import { AssistantBubble } from '@/components/portal/assistant/assistant-bubble';
import { AssistantProvider } from '@/components/portal/assistant/assistant-provider';
import { PortalMeProvider } from '@/components/portal/portal-me-context';
import { Toaster } from '@/components/ui/sonner';
import { portalApi } from '@/lib/portal-api';
import type { PortalMe } from '@/lib/types/portal';

/** `undefined` while checking, `null` when signed out (or the check failed), else the customer. */
export type SignedIn = PortalMe | null | undefined;

const SignedInContext = createContext<SignedIn>(undefined);

/** Whether a customer is signed in, kept fresh across the customer site's pages. */
export function useSignedIn(): SignedIn {
  return useContext(SignedInContext);
}

/**
 * The assistant for the whole customer site (home, log in and portal): one LiveKit session and
 * one bubble above every page, so a chat survives navigation, including a guest logging in
 * mid-conversation (AccountLink then links the session to their account). The signed-in customer
 * is re-checked on every page change, so a login or logout is picked up; the previous answer
 * stays in place while it's checked.
 */
export function CustomerAssistant({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [me, setMe] = useState<SignedIn>(undefined);

  useEffect(() => {
    let cancelled = false;
    portalApi.me().then(
      (data) => !cancelled && setMe(data),
      () => !cancelled && setMe(null)
    );
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return (
    <SignedInContext.Provider value={me}>
      <PortalMeProvider me={me ?? null}>
        <AssistantProvider>
          <AccountLink me={me} />
          {children}
          <AssistantBubble />
          {/* Lifted clear of the assistant's launcher. */}
          <Toaster position="bottom-right" offset={{ bottom: 88 }} mobileOffset={{ bottom: 88 }} />
        </AssistantProvider>
      </PortalMeProvider>
    </SignedInContext.Provider>
  );
}
