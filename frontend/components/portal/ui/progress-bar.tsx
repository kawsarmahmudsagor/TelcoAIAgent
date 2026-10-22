import { cn } from '@/lib/shadcn/utils';

export type ProgressTone = 'brand' | 'mint' | 'orange';

const FILL: Record<ProgressTone, string> = {
  brand: 'bg-brand',
  mint: 'bg-mint',
  orange: 'bg-orange',
};

/** The reference's 6px meter: `value` out of `max` (clamped), filled in brand, mint or orange. */
export function ProgressBar({
  value,
  max = 100,
  tone = 'brand',
  label,
  className,
}: {
  value: number;
  max?: number;
  tone?: ProgressTone;
  /** What the bar measures, for screen readers (e.g. "Data left"). */
  label: string;
  className?: string;
}) {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percent)}
      className={cn('bg-line mt-2 h-1.5 overflow-hidden rounded-lg', className)}
    >
      <span
        className={cn('block h-full rounded-lg motion-safe:transition-[width]', FILL[tone])}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
