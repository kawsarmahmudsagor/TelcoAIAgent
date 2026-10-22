import { cn } from '@/lib/shadcn/utils';

/**
 * The Horizon mark: two towers beside a brass sun that sits on the horizon line.
 * Towers and horizon take `currentColor`; the sun is always brass.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('size-8 shrink-0', className)}>
      <path d="M9 22a9 9 0 0 1 18 0Z" className="fill-brass" />
      <rect x="4" y="12" width="4" height="10" rx="0.5" fill="currentColor" />
      <rect x="9.5" y="7" width="4.5" height="15" rx="0.5" fill="currentColor" />
      <rect x="2" y="22" width="28" height="2" rx="1" fill="currentColor" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <BrandMark />
      <span className="font-display text-[1.0625rem] leading-none font-semibold tracking-[-0.01em]">
        Horizon Realty
      </span>
    </span>
  );
}
