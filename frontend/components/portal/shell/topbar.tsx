'use client';

import { usePathname } from 'next/navigation';
import { MenuIcon } from 'lucide-react';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import { portalNavItem } from '@/components/portal/shell/nav-items';
import { ProfileMenu } from '@/components/portal/shell/profile-menu';
import { cn } from '@/lib/shadcn/utils';

// The reference's bordered square icon button (38px, 36px on phones).
const ICON_BUTTON =
  'border-line bg-surface text-foreground hover:bg-surface2 size-[38px] rounded-[11px] border phone:size-9';

/** The eyebrow, the current page's title, the colour scheme and the account menu. */
export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const pathname = usePathname();
  const { label } = portalNavItem(pathname);

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
          <p className="text-muted-foreground phone:hidden mb-0.5 text-[11px]">
            Your digital life, made easier
          </p>
          <p className="phone:text-[17px] truncate text-xl font-extrabold tracking-[-0.5px]">
            {label}
          </p>
        </div>
      </div>

      <div className="phone:gap-[7px] flex shrink-0 items-center gap-[11px]">
        <ThemeMenu triggerClassName={ICON_BUTTON} />
        <ProfileMenu variant="avatar" />
      </div>
    </header>
  );
}
