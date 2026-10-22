import { cn } from '@/lib/shadcn/utils';

export type StatusTone = 'success' | 'pending' | 'failed' | 'open';

const TONES: Record<StatusTone, string> = {
  success: 'bg-status-success text-status-success-foreground',
  pending: 'bg-status-pending text-status-pending-foreground',
  failed: 'bg-status-failed text-status-failed-foreground',
  open: 'bg-status-open text-status-open-foreground',
};

/** The reference's small uppercase status label (transactions, cases). */
export function StatusChip({
  tone,
  children,
  className,
}: {
  tone: StatusTone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-block rounded-md px-[7px] py-1 text-[10px] leading-none font-extrabold tracking-[0.02em] whitespace-nowrap uppercase',
        TONES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
