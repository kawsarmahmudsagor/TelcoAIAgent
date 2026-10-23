import type { Metadata } from 'next';
import { NetworkView } from '@/components/dashboard/network/network-view';

export const metadata: Metadata = { title: 'Network status' };

export default function NetworkPage() {
  return <NetworkView />;
}
