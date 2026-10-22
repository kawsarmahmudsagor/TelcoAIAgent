'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { cn } from '@/lib/shadcn/utils';

type SectionLink = { readonly href: `/home#${string}`; readonly label: string };

const sectionId = (href: string) => href.slice(href.indexOf('#') + 1);

/**
 * Home-page section links with a scroll spy: the section the reader is in (or just jumped to) gets the
 * brass marker. A section counts as current once its top passes ~35% down the viewport; at the
 * very bottom of the page the last section wins, since it may be too short to reach that line.
 */
export function SectionNav({ links }: { links: readonly SectionLink[] }) {
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const sections = links
      .map((link) => document.getElementById(sectionId(link.href)))
      .filter((el): el is HTMLElement => el !== null);
    if (sections.length === 0) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      const line = window.innerHeight * 0.35;
      const atBottom =
        window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      let current: HTMLElement | null = null;
      for (const section of sections) {
        const top = section.getBoundingClientRect().top;
        if (atBottom || top <= line) {
          // Sections aren't in nav order on the page, so take the lowest one that qualifies.
          if (!current || top > current.getBoundingClientRect().top) current = section;
        }
      }
      setActive(current ? current.id : null);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [links]);

  return (
    <ul className="flex items-center gap-1">
      {links.map((link) => {
        const id = sectionId(link.href);
        const current = active === id;
        return (
          <li key={link.href}>
            {/* next/link, so jumping back to /home from another (site) page keeps the chat call. */}
            <Link
              href={link.href}
              onClick={() => setActive(id)}
              aria-current={current ? 'location' : undefined}
              className={cn(
                'focus-visible:ring-ring/50 relative block rounded-md px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px]',
                current
                  ? 'bg-brass/15 text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {link.label}
              <span
                aria-hidden="true"
                className={cn(
                  'bg-brass absolute inset-x-3 -bottom-px h-0.5 rounded-full transition-opacity',
                  current ? 'opacity-100' : 'opacity-0'
                )}
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
