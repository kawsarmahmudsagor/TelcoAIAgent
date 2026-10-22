import Link from 'next/link';
import { cn } from '@/lib/shadcn/utils';

export type LinkButtonVariant = 'primary' | 'soft' | 'outline' | 'white' | 'glass';

const VARIANTS: Record<LinkButtonVariant, string> = {
  primary: 'bg-primary text-primary-foreground shadow-[0_5px_12px_#4f46e522]',
  soft: 'bg-tint-purple text-brand dark:text-[#a9a3ff]',
  outline: 'border-line bg-surface text-foreground border',
  /** On the balance hero's indigo gradient. */
  white: 'bg-white text-[#4038a5]',
  /** On the balance hero's indigo gradient. */
  glass: 'border border-white/25 bg-white/10 text-white',
};

/** The reference's `.btn` as a link: 10px radius, 12px bold label, lifts 1px on hover. */
export function LinkButton({
  variant = 'primary',
  className,
  ...props
}: React.ComponentProps<typeof Link> & { variant?: LinkButtonVariant }) {
  return (
    <Link
      className={cn(
        'rounded-button focus-visible:ring-ring/60 inline-flex min-h-9 items-center justify-center gap-[7px] px-3.5 py-2.5 text-xs font-bold whitespace-nowrap outline-none focus-visible:ring-[3px] motion-safe:transition-transform motion-safe:duration-150 motion-safe:hover:-translate-y-px [&_svg]:size-3.5 [&_svg]:shrink-0',
        VARIANTS[variant],
        className
      )}
      {...props}
    />
  );
}

/** The reference's `.small-link`: a quiet brand-coloured text link for panel headers. */
export function SmallLink({ className, ...props }: React.ComponentProps<typeof Link>) {
  return (
    <Link
      className={cn(
        'text-brand focus-visible:ring-ring/60 inline-flex shrink-0 items-center gap-1 rounded-md p-[3px] text-[11px] font-bold whitespace-nowrap outline-none hover:underline focus-visible:ring-[3px] dark:text-[#a9a3ff] [&_svg]:size-3',
        className
      )}
      {...props}
    />
  );
}
