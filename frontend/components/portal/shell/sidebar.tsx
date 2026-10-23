'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowUpRightIcon, SparklesIcon } from 'lucide-react';
import { PORTAL_NAV, isPortalNavActive } from '@/components/portal/shell/nav-items';
import { ProfileMenu } from '@/components/portal/shell/profile-menu';
import { TelcoBrand } from '@/components/portal/telco-brand';
import { cn } from '@/lib/shadcn/utils';

const FOCUS = 'outline-none focus-visible:ring-[3px] focus-visible:ring-ring/60';

/**
 * Everything in the portal's side column: the brand, the "MY ACCOUNT" nav, the "Need a hand?"
 * card and the profile row. Shared by the fixed column and the mobile drawer; `onNavigate`
 * lets the drawer close when a link is followed.
 */
export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <div className="tablet:px-3 tablet:py-5 flex h-full min-h-0 flex-col gap-7 px-4 py-6">
      <Link
        href="/portal"
        onClick={onNavigate}
        aria-label="telco. overview"
        className={cn('self-start rounded-md px-2.5', FOCUS)}
      >
        <TelcoBrand />
      </Link>

      <nav aria-label="My account">
        <p className="text-muted-foreground mb-2 px-3 text-[10px] font-extrabold tracking-[1.5px]">
          MY ACCOUNT
        </p>
        <ul className="flex flex-col gap-1">
          {PORTAL_NAV.map((item) => {
            const active = isPortalNavActive(pathname, item.href);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-[11px] px-3 py-[11px] text-sm motion-safe:transition-colors motion-safe:duration-150',
                    FOCUS,
                    active
                      ? 'bg-accent text-brand-text font-bold'
                      : 'text-muted-foreground hover:bg-surface2 hover:text-foreground font-semibold'
                  )}
                >
                  <span className="grid w-[22px] shrink-0 place-items-center" aria-hidden="true">
                    <Icon className="size-[18px]" />
                  </span>
                  <span className="truncate">{item.label}</span>
                  {item.dot && (
                    <span
                      aria-hidden="true"
                      className="bg-mint ml-auto size-[7px] shrink-0 rounded-full"
                    />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="mt-auto">
        <div className="from-promo-from to-promo-to relative overflow-hidden rounded-[15px] bg-linear-145 p-[15px] text-white">
          <SparklesIcon
            aria-hidden="true"
            className="pointer-events-none absolute -right-3 -bottom-4 size-[84px] opacity-[0.12]"
          />
          <p className="relative mb-[5px] text-[13px] font-bold">Need a hand?</p>
          <p className="text-promo-foreground relative mb-[13px] text-[11px]">
            Get quick answers from Telco AI, any time.
          </p>
          <Link
            href="/portal/assistant"
            onClick={onNavigate}
            className="text-promo-ink relative inline-flex items-center gap-1 rounded-lg bg-white px-[11px] py-2 text-[11px] font-extrabold outline-none focus-visible:ring-[3px] focus-visible:ring-white/60"
          >
            Chat with Telco AI
            <ArrowUpRightIcon className="size-3.5" aria-hidden="true" />
          </Link>
        </div>

        <div className="border-line mt-[17px] border-t pt-3">
          <ProfileMenu variant="row" />
        </div>
      </div>
    </div>
  );
}

/** The fixed side column from 761px up; below that the topbar's menu button opens the drawer. */
export function Sidebar() {
  return (
    <aside className="bg-surface border-line phone:hidden sticky top-0 h-svh overflow-y-auto border-r">
      <SidebarContent />
    </aside>
  );
}
