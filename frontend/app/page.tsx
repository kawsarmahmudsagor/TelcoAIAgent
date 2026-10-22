import Link from 'next/link';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import { PersonaPicker } from '@/components/portal/persona-picker';
import { TelcoBrand } from '@/components/portal/telco-brand';

/** The demo's front door: choose a seeded customer to sign in to the self-care portal as. */
export default function HomePage() {
  return (
    <div className="bg-background flex min-h-svh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 pt-6 sm:px-8">
        <TelcoBrand />
        <ThemeMenu />
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-4 py-10 sm:px-8">
        <section className="rounded-hero relative overflow-hidden bg-linear-115 from-[#37328d] via-[#5148ce] to-[#6d68ee] px-6 py-8 text-white shadow-[0_14px_28px_#4d46be22] sm:px-8">
          {/* The reference hero's rings, top right. */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -top-28 -right-14 size-[270px] rounded-full border border-white/12 shadow-[0_0_0_28px_#ffffff08,0_0_0_57px_#ffffff06]"
          />
          <div className="relative max-w-2xl">
            <h1 className="text-[26px] leading-tight font-extrabold tracking-[-0.03em] sm:text-[32px]">
              Choose a customer to sign in as
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-[#d5d4ff] sm:text-base">
              This is a demo of the telco. self-care portal and its AI assistant. Each customer has
              their own balance, packages and a situation the assistant can help with.
            </p>
          </div>
        </section>

        <PersonaPicker />
      </main>

      <footer className="text-muted-foreground mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 pb-8 text-xs sm:px-8">
        <span>Demo data. No real accounts or payments.</span>
        <Link
          href="/login"
          className="text-foreground hover:text-primary focus-visible:ring-ring rounded-sm font-semibold underline-offset-4 outline-none hover:underline focus-visible:ring-2"
        >
          Admin login
        </Link>
      </footer>
    </div>
  );
}
