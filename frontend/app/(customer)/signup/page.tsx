import type { Metadata } from 'next';
import { AuthShell } from '@/components/portal/auth/auth-shell';
import { SignupForm } from '@/components/portal/auth/signup-form';
import { portalNextPath } from '@/lib/portal-next';

export const metadata: Metadata = { title: 'Create account' };

/** Customer sign up; the new account starts with ৳200 and 5 GB for 7 days. */
export default async function SignUpPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  const target = portalNextPath(typeof next === 'string' ? next : null);

  return (
    <AuthShell
      title="Create your telco. account"
      intro={
        <>
          New accounts start with <strong className="text-foreground">৳200</strong> balance and{' '}
          <strong className="text-foreground">5 GB</strong> of data for 7 days.
        </>
      }
      back={{ href: `/signin?next=${encodeURIComponent(target)}`, label: 'Back to log in' }}
    >
      <SignupForm next={target} />
    </AuthShell>
  );
}
