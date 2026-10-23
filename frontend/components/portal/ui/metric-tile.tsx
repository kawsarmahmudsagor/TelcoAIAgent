import type { LucideIcon } from 'lucide-react';
import { IconTile, type IconTileTone } from '@/components/portal/ui/icon-tile';
import { cn } from '@/lib/shadcn/utils';

/**
 * The reference's metric card: icon (and an optional badge) on top, then the label, the big
 * figure and a muted foot line.
 */
export function MetricTile({
  icon,
  tone,
  label,
  value,
  foot,
  badge,
  className,
}: {
  icon: LucideIcon;
  tone?: IconTileTone;
  label: React.ReactNode;
  value: React.ReactNode;
  foot?: React.ReactNode;
  /** Top right, e.g. a trend or a status chip. */
  badge?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'bg-surface border-line rounded-metric shadow-panel phone:p-3.5 min-w-0 border p-[18px]',
        className
      )}
    >
      <div className="phone:mb-3 mb-[15px] flex items-center justify-between gap-2">
        <IconTile icon={icon} tone={tone} />
        {badge}
      </div>
      <p className="text-muted-foreground mb-[5px] text-[11px]">{label}</p>
      <p className="phone:text-[22px] narrow:text-xl text-[25px] leading-tight font-extrabold tracking-[-0.8px] whitespace-nowrap">
        {value}
      </p>
      {foot && (
        <p className="text-muted-foreground phone:leading-normal mt-[5px] text-[10px]">{foot}</p>
      )}
    </div>
  );
}
