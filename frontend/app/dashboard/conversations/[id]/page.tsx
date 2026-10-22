import type { Metadata } from 'next';
import { ConversationDetailView } from '@/components/dashboard/conversations/conversation-detail-view';

export const metadata: Metadata = { title: 'Conversation' };

export default async function ConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ConversationDetailView id={id} />;
}
