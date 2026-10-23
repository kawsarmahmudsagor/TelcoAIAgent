import type { Metadata } from 'next';
import { BalanceUsage } from '@/components/portal/balance/balance-usage';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';

export const metadata: Metadata = { title: portalNavItemFor('/portal/balance').label };

export default function PortalBalancePage() {
  return <BalanceUsage />;
}
