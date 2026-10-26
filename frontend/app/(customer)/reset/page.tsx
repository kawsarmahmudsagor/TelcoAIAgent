import type { Metadata } from 'next';
import { AuthShell } from '@/components/portal/auth/auth-shell';
import { ResetForm } from '@/components/portal/auth/reset-form';
import { portalNextPath } from '@/lib/portal-next';

export const metadata: Metadata = { title: 'Reset password' };

/** Customer password reset with a code "sent" by SMS. */
export default async function ResetPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  const target = portalNextPath(typeof next === 'string' ? next : null);

  return (
    <AuthShell
      title="Reset your password"
      intro="Enter your number and we’ll send a code. This demo shows the SMS on the page."
      back={{ href: `/signin?next=${encodeURIComponent(target)}`, label: 'Back to log in' }}
    >
      <ResetForm next={target} />
    </AuthShell>
  );
}
