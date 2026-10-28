import Link from 'next/link';
import { ArrowLeftIcon } from 'lucide-react';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import { TelcoBrand } from '@/components/portal/telco-brand';
import { cn } from '@/lib/shadcn/utils';

/**
 * The frame of the customer's log in, sign up and password reset pages: brand and theme menu on
 * top, a back link, the page title and intro, then the page's form.
 */
export function AuthShell({
  title,
  intro,
  back = { href: '/', label: 'Back to home' },
  wide = false,
  children,
}: {
  title: string;
  intro: React.ReactNode;
  back?: { href: string; label: string };
  /** Full width (the log in page's persona grid) instead of a single form column. */
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-background flex min-h-svh flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 pt-6 sm:px-8">
        <Link
          href="/"
          aria-label="telco home"
          className="focus-visible:ring-ring/60 rounded-md outline-none focus-visible:ring-[3px]"
        >
          <TelcoBrand />
        </Link>
        <ThemeMenu />
      </header>

      <main
        className={cn(
          'mx-auto flex w-full flex-1 flex-col gap-8 px-4 py-10 sm:px-8',
          wide ? 'max-w-6xl' : 'max-w-xl'
        )}
      >
        <div className="max-w-2xl">
          <Link
            href={back.href}
            className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/60 -ml-1 inline-flex items-center gap-1.5 rounded-md p-1 text-xs font-semibold outline-none focus-visible:ring-[3px]"
          >
            <ArrowLeftIcon aria-hidden="true" className="size-3.5" />
            {back.label}
          </Link>
          <h1 className="mt-4 text-[28px] leading-tight font-extrabold tracking-[-0.03em] sm:text-[32px]">
            {title}
          </h1>
          <div className="text-muted-foreground mt-2 text-sm leading-relaxed sm:text-base">
            {intro}
          </div>
        </div>

        {children}
      </main>

      <footer className="text-muted-foreground mx-auto w-full max-w-6xl px-4 pb-8 text-xs sm:px-8">
        Demo data. No real accounts or payments.
      </footer>
    </div>
  );
}

/** A text link styled for the auth pages. */
export function AuthLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="text-primary focus-visible:ring-ring/60 rounded-sm font-semibold underline-offset-4 outline-none hover:underline focus-visible:ring-[3px]"
    >
      {children}
    </Link>
  );
}

/** The inline error box under an auth form. */
export function AuthError({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <p
      id={id}
      role="alert"
      className="bg-status-failed text-status-failed-foreground rounded-button px-4 py-3 text-sm font-medium"
    >
      {children}
    </p>
  );
}
