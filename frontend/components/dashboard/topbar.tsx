'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Loader2Icon, LogOutIcon } from 'lucide-react';
import { toast } from 'sonner';
import { locate } from '@/components/dashboard/nav-items';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api-client';

/** Where you are (section, then page), the colour scheme, who is signed in, and sign-out.
 * The page's own <h1> lives in the page (PageHeader), not here. */
export function Topbar({ username }: { username: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const [signingOut, setSigningOut] = useState(false);
  const { group, page } = locate(pathname);

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await api.logout();
      router.replace('/login');
    } catch {
      toast.error('Sign-out did not go through', {
        description: 'Check your connection and try again.',
      });
      setSigningOut(false);
    }
  }

  return (
    <header className="bg-background/85 sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b px-4 backdrop-blur-sm sm:px-8">
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap">
          {group && (
            <>
              <BreadcrumbItem className="hidden sm:inline-flex">{group}</BreadcrumbItem>
              <BreadcrumbSeparator className="hidden sm:list-item" />
            </>
          )}
          <BreadcrumbItem className="min-w-0">
            <BreadcrumbPage className="truncate">{page}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {username && (
        <span className="text-muted-foreground mr-2 hidden truncate text-sm md:inline">
          Signed in as <span className="text-foreground">{username}</span>
        </span>
      )}

      <ThemeMenu />

      <Button
        variant="outline"
        size="sm"
        onClick={handleSignOut}
        disabled={signingOut}
        aria-label={signingOut ? 'Signing out' : 'Sign out'}
      >
        {signingOut ? (
          <Loader2Icon className="animate-spin" aria-hidden="true" />
        ) : (
          <LogOutIcon aria-hidden="true" />
        )}
        <span className="hidden sm:inline">{signingOut ? 'Signing out…' : 'Sign out'}</span>
      </Button>
    </header>
  );
}
