import { RefreshCwIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/shadcn/utils';

/** What a table shows instead of rows: loading (skeleton rows of the same height, so nothing
 * jumps when data lands), an error with a retry, or an empty state that says what to do. */
export function TableState({
  loading,
  error,
  empty,
  onRetry,
  rows = 5,
}: {
  loading?: boolean;
  error?: string | null;
  /** Shown when there is nothing to list: what this is, and the action that adds one. */
  empty?: React.ReactNode;
  onRetry?: () => void;
  rows?: number;
}) {
  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 px-4 py-12 text-center" role="alert">
        <p className="text-muted-foreground max-w-md text-sm">{error}</p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCwIcon aria-hidden="true" /> Try again
          </Button>
        )}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="space-y-2 p-4" aria-busy="true" aria-label="Loading">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-3 px-4 py-14 text-center text-sm">
      {empty}
    </div>
  );
}

/** The bordered card surface every table and list sits on. */
export function Panel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('bg-card overflow-hidden rounded-lg border', className)}>{children}</div>
  );
}
