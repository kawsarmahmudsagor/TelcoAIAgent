import { Suspense } from 'react';
import type { Metadata } from 'next';
import { TransactionsView } from '@/components/dashboard/transactions/transactions-view';

export const metadata: Metadata = { title: 'Transactions' };

export default function TransactionsPage() {
  // useSearchParams (the ?status= and ?type= filters) needs a Suspense boundary.
  return (
    <Suspense>
      <TransactionsView />
    </Suspense>
  );
}
