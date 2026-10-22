import type { Metadata } from 'next';
import { OffersView } from '@/components/dashboard/offers/offers-view';

export const metadata: Metadata = { title: 'Offers' };

export default function OffersPage() {
  return <OffersView />;
}
