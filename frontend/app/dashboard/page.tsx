import type { Metadata } from 'next';
import { ControlCenter } from '@/components/dashboard/control/control-center';

export const metadata: Metadata = { title: 'Control center' };

export default function DashboardOverviewPage() {
  return <ControlCenter />;
}
