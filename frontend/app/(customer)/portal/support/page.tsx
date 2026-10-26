import type { Metadata } from 'next';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';
import { SupportView } from '@/components/portal/support/support-view';

const { label } = portalNavItemFor('/portal/support');

export const metadata: Metadata = { title: label };

export default function PortalSupportPage() {
  return <SupportView />;
}
