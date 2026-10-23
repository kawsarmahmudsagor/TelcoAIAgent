'use client';

import { useEffect, useState } from 'react';
import { portalApi } from '@/lib/portal-api';
import type { PortalMe } from '@/lib/types/portal';

/** `undefined` while checking, `null` when signed out (or the check failed), else the customer. */
export type SignedIn = PortalMe | null | undefined;

/** Whether a customer is signed in, from the `portal_session` cookie via `/api/me`. */
export function useSignedIn(): SignedIn {
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
  }, []);
  return me;
}
