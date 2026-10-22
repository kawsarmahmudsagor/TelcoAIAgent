import { Suspense } from 'react';
import type { Metadata } from 'next';
import { ChatbotView } from '@/components/dashboard/chatbot/chatbot-view';

export const metadata: Metadata = { title: 'Chatbot' };

export default function ChatbotPage() {
  // ChatbotView reads ?tab= with useSearchParams, which needs a Suspense boundary.
  return (
    <Suspense>
      <ChatbotView />
    </Suspense>
  );
}
