import { Suspense } from 'react';
import type { Metadata } from 'next';
import { LoginForm } from '@/components/brand/login-form';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import { TelcoBrand } from '@/components/portal/telco-brand';

export const metadata: Metadata = { title: 'Sign in' };

export default function LoginPage() {
  return (
    <div className="grid min-h-svh lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      {/* Brand panel: the left half from lg up, in the home page hero's indigo. */}
      <aside className="from-hero-from via-hero-via to-hero-to relative isolate hidden overflow-hidden bg-linear-[115deg] via-53% text-white lg:flex lg:flex-col lg:justify-center lg:px-14">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -top-32 -left-24 -z-10 size-[340px] rounded-full border border-white/10 shadow-[0_0_0_34px_#ffffff07,0_0_0_70px_#ffffff05]"
        />
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-28 -bottom-36 -z-10 size-[420px] rounded-full border border-white/10 shadow-[0_0_0_40px_#ffffff06,0_0_0_84px_#ffffff04]"
        />
        <div className="max-w-md">
          <p className="text-[2.75rem] leading-[1.05] font-extrabold tracking-[-0.035em] text-balance">
            Every subscriber answered. Every issue followed up.
          </p>
          <p className="text-hero-muted mt-5 text-base leading-relaxed">
            Your AI agent answers subscribers about balances, packs and network issues. This is
            where you see what it said and what happens next.
          </p>
        </div>
      </aside>

      <main className="relative flex flex-col px-6 py-6 sm:px-10">
        <div className="flex items-center justify-between gap-4">
          <TelcoBrand />
          <ThemeMenu />
        </div>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="text-3xl font-extrabold tracking-[-0.03em]">Sign in to the dashboard</h1>
          <p className="text-muted-foreground mt-2 mb-8 text-sm">
            For telco. staff. Use the account your administrator set up for you.
          </p>
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </main>
    </div>
  );
}
