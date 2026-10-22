'use client';

import { createContext, useContext } from 'react';
import type { PortalMe } from '@/lib/types/portal';

const PortalMeContext = createContext<PortalMe | null>(null);

/** Hands the signed-in customer (loaded once by the portal layout) to everything inside it. */
export function PortalMeProvider({ me, children }: { me: PortalMe; children: React.ReactNode }) {
  return <PortalMeContext.Provider value={me}>{children}</PortalMeContext.Provider>;
}

/** The signed-in customer. Only valid under `/portal`, where the layout has already loaded it. */
export function usePortalMe(): PortalMe {
  const me = useContext(PortalMeContext);
  if (!me) throw new Error('usePortalMe() must be used inside the portal layout');
  return me;
}
