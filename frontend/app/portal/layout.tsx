'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Loader2Icon, RotateCwIcon } from 'lucide-react';
import { PortalMeProvider } from '@/components/portal/portal-me-context';
import { MobileDrawer } from '@/components/portal/shell/mobile-drawer';
import { Sidebar } from '@/components/portal/shell/sidebar';
import { Topbar } from '@/components/portal/shell/topbar';
import { Toaster } from '@/components/ui/sonner';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';

/**
 * The customer portal's shell: side column (a drawer at 760px and below), topbar and content.
 * The signed-in customer is loaded once here; middleware.ts only checks the cookie exists, so a
 * 401 from this call (handled by usePortalQuery) is the real gate.
 */
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const me = usePortalQuery('me', portalApi.me);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const pathname = usePathname();

  // Close the drawer whenever the page changes (back/forward included).
  useEffect(() => setDrawerOpen(false), [pathname]);

  if (!me.data) {
    return (
      <main className="bg-background grid min-h-svh place-content-center px-4 text-sm">
        {me.error && !me.loading ? (
          <div role="alert" className="flex max-w-sm flex-col items-center gap-3 text-center">
            <p className="font-semibold">Your account did not load.</p>
            <p className="text-muted-foreground">{me.error.message}</p>
            <button
              type="button"
              onClick={me.reload}
              className="bg-primary text-primary-foreground rounded-button focus-visible:ring-ring/60 inline-flex items-center gap-2 px-3.5 py-2.5 text-xs font-bold outline-none focus-visible:ring-[3px]"
            >
              <RotateCwIcon className="size-3.5" aria-hidden="true" />
              Try again
            </button>
          </div>
        ) : (
          <span className="text-muted-foreground inline-flex items-center gap-2" role="status">
            <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
            Loading your account…
          </span>
        )}
      </main>
    );
  }

  return (
    <PortalMeProvider me={me.data}>
      {/* Task 10: the AI assistant's LiveKit session provider wraps the shell from here, and its
          floating bubble mounts beside the Toaster below. */}
      <div className="bg-background tablet:grid-cols-[215px_minmax(0,1fr)] phone:grid-cols-1 grid min-h-svh grid-cols-[244px_minmax(0,1fr)]">
        <Sidebar />
        <MobileDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />
        <div className="min-w-0">
          <Topbar onOpenMenu={() => setDrawerOpen(true)} />
          <main className="tablet:p-6 phone:px-[15px] phone:pt-5 phone:pb-[30px] mx-auto max-w-[1600px] px-[34px] pt-7 pb-10">
            {children}
          </main>
        </div>
      </div>
      <Toaster position="bottom-right" />
    </PortalMeProvider>
  );
}
