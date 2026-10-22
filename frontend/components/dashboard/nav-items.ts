import {
  BotIcon,
  BuildingIcon,
  CalendarCheckIcon,
  LayoutDashboardIcon,
  LibraryBigIcon,
  type LucideIcon,
  MessagesSquareIcon,
  PhoneOutgoingIcon,
  TagIcon,
  UsersIcon,
} from 'lucide-react';

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export interface NavGroup {
  /** null for the ungrouped Overview entry at the top. */
  label: string | null;
  items: NavItem[];
}

// Every href has a page under app/dashboard/**, and each page's <h1> is its label here.
// The incoming-call and listen routes are reachable but deliberately not listed.
export const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [{ href: '/dashboard', label: 'Overview', icon: LayoutDashboardIcon }],
  },
  {
    label: 'Agent',
    items: [
      { href: '/dashboard/chatbot', label: 'Chatbot', icon: BotIcon },
      { href: '/dashboard/knowledge', label: 'Knowledge base', icon: LibraryBigIcon },
      { href: '/dashboard/conversations', label: 'Conversations', icon: MessagesSquareIcon },
    ],
  },
  {
    label: 'CRM',
    items: [
      { href: '/dashboard/leads', label: 'Leads', icon: UsersIcon },
      { href: '/dashboard/properties', label: 'Properties', icon: BuildingIcon },
      { href: '/dashboard/offers', label: 'Offers', icon: TagIcon },
      { href: '/dashboard/schedule', label: 'Call schedule', icon: PhoneOutgoingIcon },
      { href: '/dashboard/bookings', label: 'Bookings', icon: CalendarCheckIcon },
    ],
  },
];

/** Labels for routes that are reachable but not in the nav, for the topbar breadcrumb. */
const HIDDEN_ROUTES: { prefix: string; label: string }[] = [
  { prefix: '/dashboard/incoming', label: 'Incoming call' },
  { prefix: '/dashboard/listen', label: 'Listen in' },
];

/** Overview is matched exactly; every other route is a prefix of it. */
export function isNavItemActive(pathname: string, href: string): boolean {
  if (href === '/dashboard') return pathname === '/dashboard';
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** The section and page the pathname belongs to, for the breadcrumb. */
export function locate(pathname: string): { group: string | null; page: string } {
  for (const group of NAV_GROUPS) {
    const item = group.items.find((i) => isNavItemActive(pathname, i.href));
    if (item) return { group: group.label, page: item.label };
  }
  const hidden = HIDDEN_ROUTES.find((r) => pathname.startsWith(r.prefix));
  return { group: null, page: hidden?.label ?? 'Dashboard' };
}
