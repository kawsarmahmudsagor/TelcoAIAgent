import type { Metadata } from 'next';
import { OverviewView } from '@/components/dashboard/overview/overview-view';

export const metadata: Metadata = { title: 'Control center' };

export default function DashboardOverviewPage() {
  return <OverviewView />;
}
