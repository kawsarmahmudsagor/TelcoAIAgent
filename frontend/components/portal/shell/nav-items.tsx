import {
  ArrowUpRightIcon,
  GaugeIcon,
  GiftIcon,
  HomeIcon,
  LifeBuoyIcon,
  type LucideIcon,
  PackageIcon,
  SparklesIcon,
} from 'lucide-react';

export interface PortalNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** The mint "online" dot (the AI assistant). */
  dot?: boolean;
}

// Every href has a page under app/portal/**, and the topbar's page title is its label here.
export const PORTAL_NAV: PortalNavItem[] = [
  { href: '/portal', label: 'Overview', icon: HomeIcon },
  { href: '/portal/balance', label: 'Balance & usage', icon: GaugeIcon },
  { href: '/portal/recharge', label: 'Recharge & bills', icon: ArrowUpRightIcon },
  { href: '/portal/packages', label: 'My packages', icon: PackageIcon },
  { href: '/portal/offers', label: 'Offers & rewards', icon: GiftIcon },
  { href: '/portal/support', label: 'Support cases', icon: LifeBuoyIcon },
  { href: '/portal/assistant', label: 'AI assistant', icon: SparklesIcon, dot: true },
];

/** Overview is matched exactly; every other item also matches its sub-routes. */
export function isPortalNavActive(pathname: string, href: string): boolean {
  if (href === '/portal') return pathname === '/portal';
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** The nav item for a pathname (Overview when none matches). */
export function portalNavItem(pathname: string): PortalNavItem {
  return PORTAL_NAV.find((item) => isPortalNavActive(pathname, item.href)) ?? PORTAL_NAV[0];
}

/** The nav item for an href (for the placeholder pages' titles). */
export function portalNavItemFor(href: string): PortalNavItem {
  return PORTAL_NAV.find((item) => item.href === href) ?? PORTAL_NAV[0];
}
