'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ExternalLinkIcon } from 'lucide-react';
import { BrandMark, Wordmark } from '@/components/brand/brand-mark';
import { NAV_GROUPS, isNavItemActive } from '@/components/dashboard/nav-items';
import { cn } from '@/lib/shadcn/utils';

const LINK =
  'focus-visible:ring-sidebar-ring relative flex h-10 items-center rounded-md text-sm outline-none focus-visible:ring-2 motion-safe:transition-colors';

/**
 * The nav links, grouped. `rail` renders the icon-only column used below `md` on the page;
 * the Sheet in the topbar always renders the labelled version.
 */
export function SidebarNav({
  rail = false,
  onNavigate,
}: {
  rail?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-0 flex-1 [scrollbar-width:thin] flex-col overflow-y-auto px-2 pb-3">
      {NAV_GROUPS.map((group, index) => (
        <div key={group.label ?? `group-${index}`} className={cn(index > 0 && 'mt-5')}>
          {group.label && (
            <p
              className={cn(
                'text-sidebar-foreground/55 mb-1.5 px-3 text-xs',
                rail && 'hidden md:block'
              )}
            >
              {group.label}
            </p>
          )}
          {/* On the rail, a short rule stands in for the group's name. */}
          {index > 0 && rail && (
            <span aria-hidden="true" className="bg-sidebar-border mx-2 mb-2 block h-px md:hidden" />
          )}
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const active = isNavItemActive(pathname, item.href);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? 'page' : undefined}
                    title={rail ? item.label : undefined}
                    className={cn(
                      LINK,
                      rail ? 'justify-center md:justify-start md:px-3' : 'px-3',
                      active
                        ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                        : 'text-sidebar-foreground/75 hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground'
                    )}
                  >
                    {active && (
                      <span
                        aria-hidden="true"
                        className="bg-sidebar-primary absolute inset-y-2 left-0 w-[3px] rounded-r-full"
                      />
                    )}
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span
                      className={cn(
                        'ml-3 truncate',
                        rail && 'sr-only md:not-sr-only md:ml-3 md:truncate'
                      )}
                    >
                      {item.label}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}

      <a
        href="/home"
        target="_blank"
        rel="noreferrer"
        title={rail ? 'Open the website' : undefined}
        className={cn(
          LINK,
          rail ? 'justify-center md:justify-start md:px-3' : 'px-3',
          'text-sidebar-foreground/75 hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground mt-auto'
        )}
      >
        <ExternalLinkIcon className="size-4 shrink-0" aria-hidden="true" />
        <span className={cn('ml-3', rail && 'sr-only md:not-sr-only md:ml-3')}>
          Open the website
        </span>
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    </div>
  );
}

/**
 * The evergreen panel: the brand, then the dashboard's sections with a brass marker beside the
 * current page. A labelled 15rem column from `md` up, a 56px icon rail below it.
 */
export function Sidebar() {
  return (
    <nav
      aria-label="Dashboard"
      className="bg-sidebar text-sidebar-foreground border-sidebar-border sticky top-0 flex h-svh w-14 shrink-0 flex-col border-r md:w-60"
    >
      <div className="flex h-16 shrink-0 items-center justify-center md:justify-start md:px-5">
        <Link
          href="/dashboard"
          aria-label="Horizon Realty dashboard"
          className="focus-visible:ring-sidebar-ring rounded-sm outline-none focus-visible:ring-2"
        >
          <BrandMark className="md:hidden" />
          <Wordmark className="hidden md:inline-flex" />
        </Link>
      </div>
      <SidebarNav rail />
    </nav>
  );
}
