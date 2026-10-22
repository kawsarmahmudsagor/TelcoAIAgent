import { Suspense } from 'react';
import type { Metadata } from 'next';
import { ConversationsView } from '@/components/dashboard/conversations/conversations-view';

export const metadata: Metadata = { title: 'Conversations' };

export default function ConversationsPage() {
  // Reads ?client_id= with useSearchParams, which needs a Suspense boundary.
  return (
    <Suspense>
      <ConversationsView />
    </Suspense>
  );
}
