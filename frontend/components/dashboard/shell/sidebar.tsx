'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ShieldCheckIcon, UsersRoundIcon } from 'lucide-react';
import { ADMIN_NAV, isAdminNavActive } from '@/components/dashboard/shell/nav-items';
import { TelcoBrand } from '@/components/portal/telco-brand';
import { adminApi } from '@/lib/admin-api';
import { useAdminQuery } from '@/lib/admin-query';
import { cn } from '@/lib/shadcn/utils';

const FOCUS = 'outline-none focus-visible:ring-[3px] focus-visible:ring-ring/60';

/** Customer returns to the persona picker at `/`; Admin is where you are. */
function ModeSwitch({ onNavigate }: { onNavigate?: () => void }) {
  const base =
    'flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-bold motion-safe:transition-colors';
  return (
    <div
      role="group"
      aria-label="Portal mode"
      className="bg-surface2 border-line flex gap-1 rounded-[11px] border p-1"
    >
      <Link
        href="/"
        onClick={onNavigate}
        className={cn(base, FOCUS, 'text-muted-foreground hover:text-foreground')}
      >
        <UsersRoundIcon className="size-3.5" aria-hidden="true" />
        Customer
      </Link>
      <span
        aria-current="true"
        className={cn(base, 'bg-surface text-primary border-line border shadow-sm')}
      >
        <ShieldCheckIcon className="size-3.5" aria-hidden="true" />
        Admin
      </span>
    </div>
  );
}

/** The open-case count beside "Support queue". Hidden at zero or while unknown. */
function OpenCasesBadge() {
  const stats = useAdminQuery('caseStats', adminApi.caseStats);
  const open = stats.data?.open ?? 0;
  if (open === 0) return null;
  return (
    <span className="bg-red/15 text-red ml-auto rounded-full px-2 py-0.5 text-[11px] leading-none font-extrabold tabular-nums">
      {open}
      <span className="sr-only"> open cases</span>
    </span>
  );
}

/**
 * Everything in the admin side column: the brand, the mode switch, and the OPERATIONS and AGENT
 * groups. Shared by the fixed column and the mobile drawer; `onNavigate` lets the drawer close
 * when a link is followed.
 */
export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <div className="tablet:px-3 tablet:py-5 flex h-full min-h-0 flex-col gap-6 px-4 py-6">
      <Link
        href="/dashboard"
        onClick={onNavigate}
        aria-label="telco. control center"
        className={cn('self-start rounded-md px-2.5', FOCUS)}
      >
        <TelcoBrand />
      </Link>

      <ModeSwitch onNavigate={onNavigate} />

      <nav aria-label="Admin" className="flex flex-col gap-6">
        {ADMIN_NAV.map((group) => (
          <div key={group.label}>
            <p className="text-muted-foreground mb-2 px-3 text-[10px] font-extrabold tracking-[1.5px]">
              {group.label}
            </p>
            <ul className="flex flex-col gap-1">
              {group.items.map((item) => {
                const active = isAdminNavActive(pathname, item.href);
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
                          ? 'bg-primary/10 text-primary font-bold'
                          : 'text-muted-foreground hover:bg-surface2 hover:text-foreground font-semibold'
                      )}
                    >
                      <span
                        className="grid w-[22px] shrink-0 place-items-center"
                        aria-hidden="true"
                      >
                        <Icon className="size-[18px]" />
                      </span>
                      <span className="truncate">{item.label}</span>
                      {item.badge === 'openCases' && <OpenCasesBadge />}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
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
