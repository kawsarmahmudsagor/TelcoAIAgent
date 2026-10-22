import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/shadcn/utils';

const TILE = 'bg-card flex min-h-[6.5rem] flex-col justify-between gap-3 rounded-lg border p-4';

interface KpiTileProps {
  label: string;
  icon: LucideIcon;
  /** `null` means the value could not be loaded: shown as "—", never as a fake 0. */
  value: number | string | null;
  sublabel?: string;
  /** Makes the whole tile a link to the page behind the number. */
  href?: string;
  /** Warning colour for a number that needs someone now. */
  emphasize?: boolean;
}

/** One headline number. */
export function KpiTile({ label, icon: Icon, value, sublabel, href, emphasize }: KpiTileProps) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-muted-foreground text-sm">{label}</p>
        <Icon
          aria-hidden="true"
          className={cn('text-muted-foreground size-4 shrink-0', emphasize && 'text-warning')}
        />
      </div>
      <div>
        <p
          className={cn(
            'font-display text-[2rem] leading-none font-semibold tracking-[-0.02em] tabular-nums',
            value === null && 'text-muted-foreground/60',
            emphasize && 'text-warning'
          )}
        >
          {value ?? '—'}
        </p>
        {(sublabel || value === null) && (
          <p className="text-muted-foreground mt-1.5 text-xs">
            {value === null ? 'Could not load' : sublabel}
          </p>
        )}
      </div>
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        className={cn(
          TILE,
          'hover:border-primary/40 focus-visible:ring-ring/50 outline-none focus-visible:ring-[3px] motion-safe:transition-colors'
        )}
      >
        {body}
      </Link>
    );
  }
  return <div className={TILE}>{body}</div>;
}

/** Same footprint as KpiTile, so the row never reflows when data lands. */
export function KpiTileSkeleton() {
  return (
    <div className={TILE} aria-hidden="true">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-8 w-16" />
    </div>
  );
}
