import type { Metadata } from 'next';
import { KnowledgeView } from '@/components/dashboard/knowledge/knowledge-view';

export const metadata: Metadata = { title: 'Knowledge base' };

export default function KnowledgePage() {
  return <KnowledgeView />;
}
