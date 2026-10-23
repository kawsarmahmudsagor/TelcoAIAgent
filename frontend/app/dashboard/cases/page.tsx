import { Suspense } from 'react';
import type { Metadata } from 'next';
import { CasesView } from '@/components/dashboard/cases/cases-view';

export const metadata: Metadata = { title: 'Support queue' };

export default function CasesPage() {
  // useSearchParams (the ?priority= and ?status= filters) needs a Suspense boundary.
  return (
    <Suspense>
      <CasesView />
    </Suspense>
  );
}
