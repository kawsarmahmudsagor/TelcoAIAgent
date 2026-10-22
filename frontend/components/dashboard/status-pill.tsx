import { cn } from '@/lib/shadcn/utils';

export type StatusTone =
  | 'neutral'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'accent'
  | 'brass'
  | 'muted';

const TONES: Record<StatusTone, { pill: string; dot: string }> = {
  neutral: { pill: 'bg-secondary text-secondary-foreground', dot: 'bg-foreground/55' },
  success: { pill: 'bg-success/12 text-success', dot: 'bg-success' },
  warning: { pill: 'bg-warning/12 text-warning', dot: 'bg-warning' },
  danger: { pill: 'bg-destructive/12 text-destructive', dot: 'bg-destructive' },
  info: { pill: 'bg-info/12 text-info', dot: 'bg-info' },
  accent: { pill: 'bg-primary/12 text-primary', dot: 'bg-primary' },
  brass: { pill: 'bg-brass/18 text-foreground', dot: 'bg-brass' },
  muted: { pill: 'bg-muted text-muted-foreground', dot: 'bg-muted-foreground/60' },
};

interface StatusPillProps {
  tone?: StatusTone;
  children: React.ReactNode;
  /** Extra detail on hover (e.g. why a job failed). Also read out to screen readers. */
  title?: string;
  /** The dot pulses for in-flight states (motion-safe only). */
  pulse?: boolean;
  className?: string;
}

/** A state in words, with a coloured dot beside it — never colour alone. */
export function StatusPill({
  tone = 'neutral',
  children,
  title,
  pulse,
  className,
}: StatusPillProps) {
  const colours = TONES[tone];
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        colours.pill,
        title && 'cursor-help',
        className
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'size-1.5 shrink-0 rounded-full',
          colours.dot,
          pulse && 'motion-safe:animate-pulse'
        )}
      />
      {children}
      {title && <span className="sr-only">: {title}</span>}
    </span>
  );
}
