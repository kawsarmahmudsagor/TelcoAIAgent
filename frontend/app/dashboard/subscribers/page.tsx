import { Suspense } from 'react';
import type { Metadata } from 'next';
import { SubscribersView } from '@/components/dashboard/subscribers/subscribers-view';

export const metadata: Metadata = { title: 'Subscribers' };

export default function SubscribersPage() {
  // useSearchParams (the ?id= that opens a subscriber) needs a Suspense boundary.
  return (
    <Suspense>
      <SubscribersView />
    </Suspense>
  );
}
