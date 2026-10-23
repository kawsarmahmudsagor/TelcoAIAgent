import Link from 'next/link';
import { SECTIONS } from '@/components/home/site-header';
import { TelcoBrand } from '@/components/portal/telco-brand';

const LINK =
  'text-muted-foreground hover:text-foreground focus-visible:ring-ring/60 rounded-sm text-sm outline-none focus-visible:ring-2';

/** Brand, the page's sections again, the demo note and the staff sign-in. */
export function SiteFooter() {
  return (
    <footer className="border-line mt-6 border-t">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-start justify-between gap-8 px-4 py-10 sm:px-8">
        <div className="max-w-xs">
          <TelcoBrand />
          <p className="text-muted-foreground mt-4 text-xs leading-relaxed">
            Demo data. No real accounts or payments.
          </p>
        </div>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-6 gap-y-3">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className={LINK}>
                  {s.label}
                </a>
              </li>
            ))}
            <li>
              <Link href="/login" className={LINK}>
                Admin login
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
