import { RotateCwIcon } from 'lucide-react';
import type { ApiError } from '@/lib/api-client';
import { cn } from '@/lib/shadcn/utils';

/** A grey placeholder bar while portal data loads (a span, so it can sit inside text). */
export function Bone({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('bg-line block rounded-md motion-safe:animate-pulse', className)}
    />
  );
}

/** What a card shows when its data did not load: what failed, the reason and a retry. */
export function LoadError({
  what,
  error,
  onRetry,
  className,
}: {
  /** e.g. "Your balance" — reads as "Your balance did not load." */
  what: string;
  error?: ApiError;
  onRetry(): void;
  className?: string;
}) {
  return (
    <div role="alert" className={cn('flex flex-col items-start gap-2.5 text-sm', className)}>
      <div>
        <p className="font-bold">{what} did not load.</p>
        {error?.message && <p className="text-muted-foreground mt-1 text-xs">{error.message}</p>}
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="border-line bg-surface text-foreground rounded-button focus-visible:ring-ring/60 hover:bg-surface2 inline-flex min-h-9 items-center gap-2 border px-3.5 py-2 text-xs font-bold outline-none focus-visible:ring-[3px]"
      >
        <RotateCwIcon className="size-3.5" aria-hidden="true" />
        Try again
      </button>
    </div>
  );
}
