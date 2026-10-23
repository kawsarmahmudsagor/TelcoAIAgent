import { InboxIcon } from 'lucide-react';
import { caseCategoryLabel } from '@/components/portal/support/case-categories';
import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import { formatDay } from '@/lib/telco-format';
import type { CaseStatus, CaseView } from '@/lib/types/portal';

const STATUS: Record<CaseStatus, { tone: StatusTone; label: string }> = {
  open: { tone: 'open', label: 'Open' },
  in_review: { tone: 'pending', label: 'In review' },
  resolved: { tone: 'success', label: 'Resolved' },
};

/** A case's status as the reference's chip; an unknown status shows as is. */
export function CaseStatusChip({ status }: { status: CaseStatus | string }) {
  const { tone, label }: { tone: StatusTone; label: string } = STATUS[status as CaseStatus] ?? {
    tone: 'open',
    label: status,
  };
  return <StatusChip tone={tone}>{label}</StatusChip>;
}

/** The cases as a table, or stacked cards at 760px and below. */
export function CaseTable({ cases }: { cases: CaseView[] }) {
  if (cases.length === 0) {
    return (
      <div className="flex items-center gap-3 py-3">
        <InboxIcon className="text-muted-foreground size-5 shrink-0" aria-hidden="true" />
        <p className="text-muted-foreground text-[11px]">
          No cases yet. Use New case if something looks wrong.
        </p>
      </div>
    );
  }
  return (
    <>
      <table className="phone:hidden w-full border-collapse text-left">
        <caption className="sr-only">Your support requests, newest first</caption>
        <thead>
          <tr className="text-muted-foreground border-line border-b text-[11px]">
            <th scope="col" className="py-2.5 pr-3 font-semibold">
              Case ID
            </th>
            <th scope="col" className="py-2.5 pr-3 font-semibold">
              Issue
            </th>
            <th scope="col" className="py-2.5 pr-3 font-semibold whitespace-nowrap">
              Created
            </th>
            <th scope="col" className="py-2.5 pr-3 font-semibold whitespace-nowrap">
              Last update
            </th>
            <th scope="col" className="py-2.5 font-semibold">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.ref} className="border-line border-b text-xs last:border-b-0">
              <th scope="row" className="py-3.5 pr-3 text-left font-bold whitespace-nowrap">
                {c.ref}
              </th>
              <td className="max-w-[320px] min-w-0 py-3.5 pr-3">
                <p className="truncate font-bold">{caseCategoryLabel(c.category)}</p>
                <p className="text-muted-foreground truncate text-[11px]">{c.description}</p>
              </td>
              <td className="py-3.5 pr-3 whitespace-nowrap">{formatDay(c.created_at)}</td>
              <td className="py-3.5 pr-3 whitespace-nowrap">{formatDay(c.updated_at)}</td>
              <td className="py-3.5">
                <CaseStatusChip status={c.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="phone:block hidden">
        {cases.map((c) => (
          <li
            key={c.ref}
            className="border-line border-b py-3.5 first:pt-0 last:border-b-0 last:pb-0"
          >
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <p className="text-xs font-bold">{c.ref}</p>
              <CaseStatusChip status={c.status} />
            </div>
            <p className="text-xs font-bold">{caseCategoryLabel(c.category)}</p>
            <p className="text-muted-foreground mt-0.5 line-clamp-2 text-[11px]">{c.description}</p>
            <p className="text-muted-foreground mt-1.5 text-[10px]">
              Created {formatDay(c.created_at)} · Updated {formatDay(c.updated_at)}
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}
