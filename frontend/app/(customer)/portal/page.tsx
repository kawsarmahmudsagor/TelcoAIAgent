import type { Metadata } from 'next';
import { Overview } from '@/components/portal/overview/overview';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';

export const metadata: Metadata = { title: portalNavItemFor('/portal').label };

export default function PortalOverviewPage() {
  return <Overview />;
}
