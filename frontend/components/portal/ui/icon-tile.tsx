import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/shadcn/utils';

export type IconTileTone = 'purple' | 'green' | 'orange' | 'pink';

// The reference's tint pairs: a soft well with the matching accent for the glyph.
const TONES: Record<IconTileTone, string> = {
  purple: 'bg-tint-purple text-brand dark:text-[#a9a3ff]',
  green: 'bg-tint-green text-mint',
  orange: 'bg-tint-orange text-orange',
  pink: 'bg-tint-pink text-red',
};

const SIZES = {
  /** Metric cards (36px, 32px on phones). */
  md: 'size-9 rounded-[11px] phone:size-8 [&_svg]:size-[17px]',
  /** Usage lines and shortcuts (38px). */
  lg: 'size-[38px] rounded-xl [&_svg]:size-[18px]',
} as const;

/** A decorative icon in a tinted rounded square. */
export function IconTile({
  icon: Icon,
  tone = 'purple',
  size = 'md',
  className,
}: {
  icon: LucideIcon;
  tone?: IconTileTone;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn('grid shrink-0 place-items-center', TONES[tone], SIZES[size], className)}
    >
      <Icon />
    </span>
  );
}
