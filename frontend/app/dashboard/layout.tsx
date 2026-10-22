'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2Icon } from 'lucide-react';
import { ScheduledCallWatcher } from '@/components/app/scheduled-call-watcher';
import { Sidebar } from '@/components/dashboard/sidebar';
import { Topbar } from '@/components/dashboard/topbar';
import { Toaster } from '@/components/ui/sonner';
import { api } from '@/lib/api-client';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  // undefined = still checking. middleware.ts only checks that a cookie exists; this call is
  // the real gate (and the only one when the API is on another origin).
  const [username, setUsername] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    api
      .me()
      .then((me) => setUsername(me.username))
      .catch(() => router.replace('/login'));
  }, [router]);

  if (username === undefined) {
    return (
      <main className="text-muted-foreground grid h-svh place-content-center text-sm">
        <span className="inline-flex items-center gap-2" role="status">
          <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
          Checking your session…
        </span>
      </main>
    );
  }

  return (
    <div className="flex min-h-svh">
      <ScheduledCallWatcher />
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar username={username} />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-8 sm:py-8">
          {children}
        </main>
      </div>
      <Toaster position="bottom-right" />
    </div>
  );
}
