import Link from 'next/link';
import { Wordmark } from '@/components/brand/brand-mark';
import { OpenChatButton } from '@/components/chat-bubble/open-chat-button';
import { ThemeMenu } from '@/components/dashboard/theme-menu';
import { SectionNav } from '@/components/home/section-nav';
import { Button } from '@/components/ui/button';

// Absolute (`/home#…`) so they also work from other public pages, such as a property page.
export const SECTION_LINKS = [
  { href: '/home#homes', label: 'Featured homes' },
  { href: '/home#areas', label: 'Areas' },
  { href: '/home#how-it-works', label: 'How it works' },
  { href: '/home#contact', label: 'Contact' },
] as const;

/**
 * Sticky public-site header: brand, home-page sections, the full property list, staff login and
 * the agent CTA.
 */
export function SiteNav() {
  return (
    <header className="bg-background/85 sticky top-0 z-40 border-b backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-8">
        <Link
          href="/home"
          className="focus-visible:ring-ring/50 -m-1 rounded-md p-1 outline-none focus-visible:ring-[3px]"
        >
          <Wordmark />
          <span className="sr-only">, home</span>
        </Link>
        <nav aria-label="Page sections" className="hidden lg:block">
          <SectionNav links={SECTION_LINKS} />
        </nav>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <ThemeMenu />
          {/* Not one of SECTION_LINKS: those are /home anchors that SectionNav scroll-spies. */}
          <Button asChild variant="ghost" className="hidden md:inline-flex">
            <Link href="/properties">All properties</Link>
          </Button>
          <Button asChild variant="ghost" className="hidden sm:inline-flex">
            <Link href="/login">Staff login</Link>
          </Button>
          <OpenChatButton>
            <span className="sm:hidden">Ask our agent</span>
            <span className="hidden sm:inline">Talk to our AI agent</span>
          </OpenChatButton>
        </div>
      </div>
    </header>
  );
}
