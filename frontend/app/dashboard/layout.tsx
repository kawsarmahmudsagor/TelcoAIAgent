'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Loader2Icon } from 'lucide-react';
import { MobileDrawer } from '@/components/dashboard/shell/mobile-drawer';
import { Sidebar } from '@/components/dashboard/shell/sidebar';
import { Topbar } from '@/components/dashboard/shell/topbar';
import { Toaster } from '@/components/ui/sonner';
import { api } from '@/lib/api-client';

/**
 * The admin portal's shell: side column (a drawer at 760px and below), topbar and content.
 * middleware.ts only checks that the `session` cookie exists; the `api.me()` call here is the
 * real gate (and the only one when the API is on another origin).
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  // undefined = still checking.
  const [username, setUsername] = useState<string | null | undefined>(undefined);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    api
      .me()
      .then((me) => setUsername(me.username))
      .catch(() => router.replace('/login'));
  }, [router]);

  // Close the drawer whenever the page changes (back/forward included).
  useEffect(() => setDrawerOpen(false), [pathname]);

  if (username === undefined) {
    return (
      <main className="text-muted-foreground bg-background grid h-svh place-content-center text-sm">
        <span className="inline-flex items-center gap-2" role="status">
          <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
          Checking your session…
        </span>
      </main>
    );
  }

  return (
    <div className="bg-background tablet:grid-cols-[215px_minmax(0,1fr)] phone:grid-cols-1 grid min-h-svh grid-cols-[244px_minmax(0,1fr)]">
      <Sidebar />
      <MobileDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />
      <div className="min-w-0">
        <Topbar username={username} onOpenMenu={() => setDrawerOpen(true)} />
        <main className="tablet:p-6 phone:px-[15px] phone:pt-5 phone:pb-[30px] mx-auto max-w-[1600px] px-[34px] pt-7 pb-10">
          {children}
        </main>
      </div>
      <Toaster position="bottom-right" />
    </div>
  );
}
