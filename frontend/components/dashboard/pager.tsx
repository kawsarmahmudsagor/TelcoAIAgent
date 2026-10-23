import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import { PortalButton } from '@/components/portal/ui/link-button';

/** "Showing 1–25 of 140" with Previous / Next. `page` is zero-based. */
export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : page * pageSize + 1;
  const to = Math.min(total, (page + 1) * pageSize);
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
      <p className="text-muted-foreground text-[11px]" aria-live="polite">
        Showing {from}–{to} of {total.toLocaleString('en-IN')}
      </p>
      <div className="flex items-center gap-2">
        <PortalButton variant="outline" disabled={page === 0} onClick={() => onPage(page - 1)}>
          <ChevronLeftIcon aria-hidden="true" />
          Previous
        </PortalButton>
        <span className="text-muted-foreground text-[11px] tabular-nums">
          Page {page + 1} of {pages}
        </span>
        <PortalButton
          variant="outline"
          disabled={page + 1 >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
          <ChevronRightIcon aria-hidden="true" />
        </PortalButton>
      </div>
    </div>
  );
}
