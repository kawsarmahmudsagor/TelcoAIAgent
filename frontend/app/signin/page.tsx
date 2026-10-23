import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeftIcon } from 'lucide-react';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import { PersonaPicker } from '@/components/portal/persona-picker';
import { TelcoBrand } from '@/components/portal/telco-brand';
import { portalNextPath } from '@/lib/portal-next';

export const metadata: Metadata = { title: 'Log in' };

/** Customer log in: pick one of the seeded demo customers, then continue to `?next=`. */
export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  const target = portalNextPath(typeof next === 'string' ? next : null);

  return (
    <div className="bg-background flex min-h-svh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 pt-6 sm:px-8">
        <Link
          href="/"
          aria-label="telco. home"
          className="focus-visible:ring-ring/60 rounded-md outline-none focus-visible:ring-[3px]"
        >
          <TelcoBrand />
        </Link>
        <ThemeMenu />
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-4 py-10 sm:px-8">
        <div className="max-w-2xl">
          <Link
            href="/"
            className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/60 -ml-1 inline-flex items-center gap-1.5 rounded-md p-1 text-xs font-semibold outline-none focus-visible:ring-[3px]"
          >
            <ArrowLeftIcon aria-hidden="true" className="size-3.5" />
            Back to home
          </Link>
          <h1 className="mt-4 text-[28px] leading-tight font-extrabold tracking-[-0.03em] sm:text-[32px]">
            Log in to My telco.
          </h1>
          <p className="text-muted-foreground mt-2 text-sm leading-relaxed sm:text-base">
            This demo has no passwords. Choose a customer to log in as; each one has their own
            balance, packs and a situation the assistant can help with.
          </p>
        </div>

        <PersonaPicker next={target} />
      </main>

      <footer className="text-muted-foreground mx-auto w-full max-w-6xl px-4 pb-8 text-xs sm:px-8">
        Demo data. No real accounts or payments.
      </footer>
    </div>
  );
}
