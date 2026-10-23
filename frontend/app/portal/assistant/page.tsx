import { Suspense } from 'react';
import type { Metadata } from 'next';
import { AssistantPage } from '@/components/portal/assistant/assistant-page';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';

const { label } = portalNavItemFor('/portal/assistant');

export const metadata: Metadata = { title: label };

export default function PortalAssistantPage() {
  return (
    // useSearchParams (`?q=`) needs a Suspense boundary.
    <Suspense>
      <AssistantPage />
    </Suspense>
  );
}
