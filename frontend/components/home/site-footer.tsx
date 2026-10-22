import Link from 'next/link';
import { Wordmark } from '@/components/brand/brand-mark';
import { SECTION_LINKS } from '@/components/home/site-nav';
import { cn } from '@/lib/shadcn/utils';

const CONTAINER = 'mx-auto max-w-6xl px-4 sm:px-8';

/** Public-site footer: brand blurb, the home page's sections and staff login. */
export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className={cn(CONTAINER, 'flex flex-col gap-8 py-10 md:flex-row md:items-start')}>
        <div className="md:flex-1">
          <Wordmark />
          <p className="text-muted-foreground mt-3 max-w-xs text-sm leading-relaxed">
            Flats, family homes, offices and land across Dhaka, with an AI agent that answers at any
            hour.
          </p>
        </div>
        <nav aria-label="Footer">
          <ul className="grid grid-cols-2 gap-x-10 gap-y-1 text-sm sm:flex sm:gap-x-2">
            {SECTION_LINKS.map((link) => (
              <li key={link.href}>
                {/* next/link, so leaving another (site) page keeps the chat call alive. */}
                <Link
                  href={link.href}
                  className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 inline-flex min-h-10 items-center rounded-md outline-none focus-visible:ring-[3px] sm:px-3"
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <Link
                href="/login"
                className="text-foreground focus-visible:ring-ring/50 inline-flex min-h-10 items-center rounded-md font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] sm:px-3"
              >
                Staff login
              </Link>
            </li>
          </ul>
        </nav>
      </div>
      <div className={cn(CONTAINER, 'text-muted-foreground border-t py-6 text-xs')}>
        © {new Date().getFullYear()} Horizon Realty, Dhaka.
      </div>
    </footer>
  );
}
