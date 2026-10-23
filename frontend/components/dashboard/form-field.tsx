import { CircleAlertIcon } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/shadcn/utils';

/**
 * Label above, control, then a hint or the error that replaces it. The control gets
 * `aria-describedby`/`aria-invalid` through the render prop, so the message is read out with it.
 */
export function FormField({
  id,
  label,
  hint,
  error,
  aside,
  className,
  children,
}: {
  id: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: string | null;
  /** Right of the label: a small action (Reset, Edit) or a badge. */
  aside?: React.ReactNode;
  className?: string;
  children: (control: {
    id: string;
    'aria-describedby'?: string;
    'aria-invalid'?: boolean;
  }) => React.ReactNode;
}) {
  const messageId = `${id}-message`;
  const hasMessage = Boolean(error || hint);
  return (
    <div className={cn('grid min-w-0 content-start gap-2', className)}>
      <div className="flex min-h-5 flex-wrap items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {aside}
      </div>
      {children({
        id,
        'aria-describedby': hasMessage ? messageId : undefined,
        'aria-invalid': error ? true : undefined,
      })}
      {error ? (
        <p id={messageId} className="text-destructive flex gap-1.5 text-xs" role="alert">
          <CircleAlertIcon className="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p id={messageId} className="text-muted-foreground text-xs">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** A native `<select>` that matches `Input` (use with FormField's control props). */
export const SELECT =
  'border-input dark:bg-input/30 focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:border-destructive h-9 w-full min-w-0 rounded-md border bg-transparent px-2.5 text-base shadow-xs outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50 md:text-sm';
