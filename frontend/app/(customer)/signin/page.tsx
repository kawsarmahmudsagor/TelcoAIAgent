import type { Metadata } from 'next';
import { AuthShell } from '@/components/portal/auth/auth-shell';
import { PasswordLoginForm } from '@/components/portal/auth/password-login-form';
import { PersonaPicker } from '@/components/portal/persona-picker';
import { portalNextPath } from '@/lib/portal-next';

export const metadata: Metadata = { title: 'Log in' };

/**
 * Customer log in: number + password for an account, or one click on a seeded demo customer.
 * Either way it continues to `?next=`.
 */
export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  const target = portalNextPath(typeof next === 'string' ? next : null);

  return (
    <AuthShell
      wide
      title="Log in to My telco."
      intro="Log in with your number and password, or try one of the demo customers below."
    >
      <div className="w-full max-w-md">
        <PasswordLoginForm next={target} />
      </div>

      <section aria-labelledby="demo-customers" className="flex flex-col gap-4">
        <div>
          <h2 id="demo-customers" className="text-lg font-bold tracking-[-0.01em]">
            Or try a demo customer
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            No password needed. Each one has their own balance, packs and a situation the assistant
            can help with.
          </p>
        </div>
        <PersonaPicker next={target} />
      </section>
    </AuthShell>
  );
}
