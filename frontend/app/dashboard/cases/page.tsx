import type { Metadata } from 'next';
import { ComingSoon } from '@/components/dashboard/shell/coming-soon';
import { adminNavItemFor } from '@/components/dashboard/shell/nav-items';

const HREF = '/dashboard/cases';

export const metadata: Metadata = { title: adminNavItemFor(HREF).label };

export default function AdminPlaceholderPage() {
  return <ComingSoon href={HREF} />;
}
