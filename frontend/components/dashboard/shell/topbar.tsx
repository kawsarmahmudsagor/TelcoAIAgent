'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { ChevronDownIcon, LogOutIcon, MenuIcon } from 'lucide-react';
import { toast } from 'sonner';
import { adminPageTitle } from '@/components/dashboard/shell/nav-items';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { api } from '@/lib/api-client';
import { cn } from '@/lib/shadcn/utils';
import { initials } from '@/lib/telco-format';

// The bordered square icon button (38px, 36px on phones), as in the customer portal.
const ICON_BUTTON =
  'border-line bg-surface text-foreground hover:bg-surface2 size-[38px] rounded-[11px] border phone:size-9';

/** The eyebrow, the current page's title, the colour scheme and the admin menu. */
export function Topbar({
  username,
  onOpenMenu,
}: {
  username: string | null;
  onOpenMenu: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const title = adminPageTitle(pathname);
  const name = username ?? 'Admin';

  async function logOut() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await api.logout();
      router.replace('/login');
    } catch {
      toast.error('Log out did not go through', {
        description: 'Check your connection and try again.',
      });
      setLoggingOut(false);
    }
  }

  return (
    <header className="bg-surface border-line tablet:px-6 phone:h-[68px] phone:px-4 sticky top-0 z-[5] flex h-[76px] items-center justify-between gap-5 border-b px-[34px]">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label="Open menu"
          className={cn(
            ICON_BUTTON,
            'focus-visible:ring-ring/60 phone:inline-grid hidden place-items-center outline-none focus-visible:ring-[3px]'
          )}
        >
          <MenuIcon className="size-[18px]" aria-hidden="true" />
        </button>
        <div className="min-w-0">
          <p className="text-muted-foreground phone:hidden mb-0.5 text-[11px]">Operations</p>
          <p className="phone:text-[17px] truncate text-xl font-extrabold tracking-[-0.5px]">
            {title}
          </p>
        </div>
      </div>

      <div className="phone:gap-[7px] flex shrink-0 items-center gap-[11px]">
        <ThemeMenu triggerClassName={ICON_BUTTON} />
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`Admin menu for ${name}`}
            className="hover:bg-surface2 focus-visible:ring-ring/60 flex items-center gap-2 rounded-full py-0.5 pr-2 pl-0.5 outline-none focus-visible:ring-[3px] motion-safe:transition-colors"
          >
            <span
              aria-hidden="true"
              className="bg-primary text-primary-foreground grid size-9 place-items-center rounded-full text-[11px] font-extrabold"
            >
              {initials(name)}
            </span>
            <ChevronDownIcon
              className="text-muted-foreground phone:hidden size-4"
              aria-hidden="true"
            />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <span className="block truncate text-sm font-semibold">{name}</span>
              <span className="text-muted-foreground block truncate text-xs">Administrator</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={loggingOut} onSelect={() => void logOut()}>
              <LogOutIcon aria-hidden="true" />
              {loggingOut ? 'Logging out…' : 'Log out'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
