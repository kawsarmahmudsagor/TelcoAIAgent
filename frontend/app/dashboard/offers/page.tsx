import { Suspense } from 'react';
import type { Metadata } from 'next';
import { OffersView } from '@/components/dashboard/offers/offers-view';

export const metadata: Metadata = { title: 'Offers' };

export default function OffersPage() {
  // The kind filter lives in ?kind=, which needs a Suspense boundary.
  return (
    <Suspense>
      <OffersView />
    </Suspense>
  );
}
