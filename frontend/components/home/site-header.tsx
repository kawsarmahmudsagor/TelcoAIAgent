import Link from 'next/link';
import { LayoutDashboardIcon, LogInIcon } from 'lucide-react';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import type { SignedIn } from '@/components/home/use-signed-in';
import { TelcoBrand } from '@/components/portal/telco-brand';
import { LinkButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';
import { initials } from '@/lib/telco-format';

export const SECTIONS = [
  { id: 'packs', label: 'Packs' },
  { id: 'recharge', label: 'Recharge' },
  { id: 'assistant', label: 'Telco AI' },
  { id: 'help', label: 'Help' },
] as const;

const FOCUS = 'outline-none focus-visible:ring-[3px] focus-visible:ring-ring/60';

/** The account action: "Log in" signed out, the customer and "My dashboard" signed in. */
export function AccountAction({ me, className }: { me: SignedIn; className?: string }) {
  if (me === undefined) {
    return <span aria-hidden="true" className={cn('h-9 w-[118px]', className)} />;
  }
  if (me === null) {
    return (
      <LinkButton href="/signin" className={className}>
        <LogInIcon aria-hidden="true" />
        Log in
      </LinkButton>
    );
  }
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <span
        aria-hidden="true"
        className="from-persona-1-from to-persona-1-to phone:hidden grid size-9 place-items-center rounded-full bg-linear-135 text-xs font-extrabold text-white"
      >
        {initials(me.full_name)}
      </span>
      <LinkButton href="/portal" aria-label={`My dashboard, signed in as ${me.full_name}`}>
        <LayoutDashboardIcon aria-hidden="true" />
        My dashboard
      </LinkButton>
    </span>
  );
}

/** Brand, in-page section links (from 761px up), theme and the account action. */
export function SiteHeader({ me }: { me: SignedIn }) {
  return (
    <header className="bg-background/85 border-line sticky top-0 z-30 border-b backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-6 px-4 sm:px-8">
        <Link href="/" aria-label="telco. home" className={cn('rounded-md', FOCUS)}>
          <TelcoBrand />
        </Link>
        <nav aria-label="Sections" className="phone:hidden ml-2">
          <ul className="flex items-center gap-1">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className={cn(
                    'text-muted-foreground hover:text-foreground rounded-md px-3 py-2 text-sm font-semibold',
                    FOCUS
                  )}
                >
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <ThemeMenu />
          <AccountAction me={me} />
        </div>
      </div>
    </header>
  );
}
