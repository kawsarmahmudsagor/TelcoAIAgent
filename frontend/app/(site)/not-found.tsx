import Link from 'next/link';
import { SiteFooter } from '@/components/home/site-footer';
import { SiteNav } from '@/components/home/site-nav';
import { Button } from '@/components/ui/button';

/** In-layout 404 for public pages, so the chat bubble (and any call in it) stays up. */
export default function SiteNotFound() {
  return (
    <div className="flex min-h-svh flex-col">
      <SiteNav />
      <main id="main" className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-20 sm:px-8">
        <p className="text-brass text-sm font-semibold tracking-wide uppercase">404</p>
        <h1 className="font-display mt-2 text-3xl font-semibold tracking-[-0.02em] sm:text-4xl">
          We couldn’t find that page
        </h1>
        <p className="text-muted-foreground mt-3 max-w-xl text-lg leading-relaxed">
          The listing may have been let or sold, or the link is out of date. Our AI agent can still
          search everything we hold.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/home#homes">See featured homes</Link>
          </Button>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
