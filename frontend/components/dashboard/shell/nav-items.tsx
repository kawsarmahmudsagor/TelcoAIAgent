import {
  ArrowUpRightIcon,
  BotIcon,
  LayoutDashboardIcon,
  LibraryBigIcon,
  LifeBuoyIcon,
  type LucideIcon,
  MessagesSquareIcon,
  RadioTowerIcon,
  SparklesIcon,
  TagIcon,
  UsersIcon,
} from 'lucide-react';

export interface AdminNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /**
   * A count beside the label: open cases (the support queue), or KB docs edited since they were
   * embedded (the knowledge base).
   */
  badge?: 'openCases' | 'kbChanges';
}

export interface AdminNavGroup {
  label: string;
  items: AdminNavItem[];
}

// Every href has a page under app/dashboard/**; the topbar's page title is its label here.
export const ADMIN_NAV: AdminNavGroup[] = [
  {
    label: 'OPERATIONS',
    items: [
      { href: '/dashboard', label: 'Control center', icon: LayoutDashboardIcon },
      { href: '/dashboard/subscribers', label: 'Subscribers', icon: UsersIcon },
      { href: '/dashboard/transactions', label: 'Transactions', icon: ArrowUpRightIcon },
      { href: '/dashboard/cases', label: 'Support queue', icon: LifeBuoyIcon, badge: 'openCases' },
      { href: '/dashboard/network', label: 'Network status', icon: RadioTowerIcon },
      { href: '/dashboard/ai-monitor', label: 'AI monitor', icon: SparklesIcon },
    ],
  },
  {
    label: 'AGENT',
    items: [
      { href: '/dashboard/chatbot', label: 'Chatbot', icon: BotIcon },
      {
        href: '/dashboard/knowledge',
        label: 'Knowledge base',
        icon: LibraryBigIcon,
        badge: 'kbChanges',
      },
      { href: '/dashboard/conversations', label: 'Conversations', icon: MessagesSquareIcon },
      { href: '/dashboard/offers', label: 'Offers', icon: TagIcon },
    ],
  },
];

/** Labels for routes that are reachable but not in the nav. */
const HIDDEN_ROUTES: { prefix: string; label: string }[] = [
  { prefix: '/dashboard/listen', label: 'Listen in' },
];

const ALL_ITEMS = ADMIN_NAV.flatMap((group) => group.items);

/** Control center is matched exactly; every other item also matches its sub-routes. */
export function isAdminNavActive(pathname: string, href: string): boolean {
  if (href === '/dashboard') return pathname === '/dashboard';
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** The page title for a pathname (Control center when none matches). */
export function adminPageTitle(pathname: string): string {
  const item = ALL_ITEMS.find((i) => isAdminNavActive(pathname, i.href));
  if (item) return item.label;
  return HIDDEN_ROUTES.find((r) => pathname.startsWith(r.prefix))?.label ?? 'Control center';
}

/** The nav item for an href (for the placeholder pages' titles). */
export function adminNavItemFor(href: string): AdminNavItem {
  return ALL_ITEMS.find((i) => i.href === href) ?? ALL_ITEMS[0];
}
