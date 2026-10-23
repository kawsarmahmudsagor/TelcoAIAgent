import { Suspense } from 'react';
import type { Metadata } from 'next';
import { Wordmark } from '@/components/brand/brand-mark';
import { LoginForm } from '@/components/brand/login-form';
import { Skyline } from '@/components/brand/skyline';
import { ThemeMenu } from '@/components/dashboard/theme-menu';

export const metadata: Metadata = { title: 'Sign in' };

export default function LoginPage() {
  return (
    <div className="grid min-h-svh grid-rows-[auto_1fr] lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:grid-rows-1">
      {/* Brand panel: a band on phones, the left half from lg up. */}
      <aside className="bg-sidebar text-sidebar-foreground relative flex flex-col overflow-hidden">
        <div className="relative z-10 flex flex-col gap-10 px-6 pt-6 pb-8 sm:px-10 lg:px-14 lg:pt-12">
          <Wordmark />
          <div className="hidden max-w-md lg:block">
            <p className="font-display text-[2.75rem] leading-[1.05] font-semibold tracking-[-0.025em] text-balance">
              Every enquiry answered. Every viewing booked.
            </p>
            <p className="text-sidebar-foreground/75 mt-5 text-base leading-relaxed">
              Your AI agent answers subscribers about balances, packs and network issues. This is
              where you see what it said and what happens next.
            </p>
          </div>
        </div>
        <Skyline className="mt-auto hidden h-64 lg:block xl:h-80" />
      </aside>

      <main className="relative flex flex-col px-6 py-8 sm:px-10">
        <div className="flex justify-end">
          <ThemeMenu />
        </div>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <h1 className="font-display text-3xl font-semibold tracking-[-0.02em]">
            Sign in to the dashboard
          </h1>
          <p className="text-muted-foreground mt-2 mb-8 text-sm">
            For Horizon Realty staff. Use the account your administrator set up for you.
          </p>
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </main>
    </div>
  );
}
