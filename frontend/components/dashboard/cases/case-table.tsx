import { PersonCell } from '@/components/dashboard/person-cell';
import { caseCategoryLabel } from '@/components/portal/support/case-categories';
import { CaseStatusChip } from '@/components/portal/support/case-table';
import { PortalButton } from '@/components/portal/ui/link-button';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { formatAge, formatDayTime } from '@/lib/telco-format';
import type { AdminCase } from '@/lib/types/admin';
import type { CaseStatus } from '@/lib/types/portal';

export function PriorityChip({ priority }: { priority: string }) {
  return priority === 'high' ? (
    <StatusChip tone="failed">High</StatusChip>
  ) : (
    <StatusChip tone="open">Normal</StatusChip>
  );
}

/** Open cases show how long they have waited; resolved ones how long they took. */
function ageText(c: AdminCase, now: Date): string {
  return c.status === 'resolved' && c.resolved_at
    ? formatAge(c.created_at, new Date(c.resolved_at))
    : formatAge(c.created_at, now);
}

function ageTitle(c: AdminCase): string {
  return `${c.status === 'resolved' ? 'Took this long to resolve. ' : ''}Opened ${formatDayTime(c.created_at)}`;
}

function Person({ c }: { c: AdminCase }) {
  return <PersonCell name={c.subscriber_name} msisdn={c.msisdn_masked} />;
}

/** The next step(s) for a case: start review and resolve while open, reopen once resolved. */
function Actions({
  c,
  busy,
  onChange,
}: {
  c: AdminCase;
  busy: boolean;
  onChange: (c: AdminCase, status: CaseStatus) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {c.status === 'open' && (
        <PortalButton
          variant="outline"
          disabled={busy}
          onClick={() => onChange(c, 'in_review')}
          aria-label={`Start review of ${c.ref}`}
        >
          Start review
        </PortalButton>
      )}
      {c.status !== 'resolved' ? (
        <PortalButton
          variant="soft"
          disabled={busy}
          onClick={() => onChange(c, 'resolved')}
          aria-label={`Resolve ${c.ref}`}
        >
          Resolve ✓
        </PortalButton>
      ) : (
        <PortalButton
          variant="outline"
          disabled={busy}
          onClick={() => onChange(c, 'open')}
          aria-label={`Reopen ${c.ref}`}
        >
          Reopen
        </PortalButton>
      )}
    </div>
  );
}

interface CaseTableProps {
  items: AdminCase[];
  /** Refs whose status change is in flight. */
  busy: ReadonlySet<string>;
  onChange: (c: AdminCase, status: CaseStatus) => void;
}

/** A table, or stacked cards at 1100px and below. */
export function CaseQueueTable({ items, busy, onChange }: CaseTableProps) {
  const now = new Date();
  return (
    <>
      <table className="tablet:hidden w-full border-collapse text-left">
        <caption className="sr-only">Support cases, high priority first</caption>
        <thead>
          <tr className="text-muted-foreground border-line border-b text-[11px]">
            {['Case', 'Subscriber', 'Issue', 'Priority', 'Age', 'Status'].map((h) => (
              <th key={h} scope="col" className="py-2.5 pr-3 font-semibold whitespace-nowrap">
                {h}
              </th>
            ))}
            <th scope="col" className="py-2.5">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.ref} className="border-line border-b text-xs last:border-b-0">
              <th scope="row" className="py-3 pr-3 text-left font-bold whitespace-nowrap">
                {c.ref}
              </th>
              <td className="max-w-[200px] py-3 pr-3">
                <Person c={c} />
              </td>
              <td className="max-w-[280px] min-w-0 py-3 pr-3">
                <p className="truncate font-bold">{caseCategoryLabel(c.category)}</p>
                <p className="text-muted-foreground truncate text-[11px]" title={c.description}>
                  {c.description}
                </p>
              </td>
              <td className="py-3 pr-3">
                <PriorityChip priority={c.priority} />
              </td>
              <td className="py-3 pr-3 whitespace-nowrap tabular-nums" title={ageTitle(c)}>
                {ageText(c, now)}
              </td>
              <td className="py-3 pr-3">
                <CaseStatusChip status={c.status} />
              </td>
              <td className="py-3">
                <Actions c={c} busy={busy.has(c.ref)} onChange={onChange} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="tablet:block hidden">
        {items.map((c) => (
          <li
            key={c.ref}
            className="border-line border-b py-3.5 first:pt-0 last:border-b-0 last:pb-0"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <Person c={c} />
              <div className="flex shrink-0 items-center gap-1.5">
                <PriorityChip priority={c.priority} />
                <CaseStatusChip status={c.status} />
              </div>
            </div>
            <p className="text-xs font-bold">
              {c.ref} · {caseCategoryLabel(c.category)}
            </p>
            <p className="text-muted-foreground mt-0.5 line-clamp-2 text-[11px]">{c.description}</p>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-muted-foreground text-[10px]" title={ageTitle(c)}>
                {c.status === 'resolved' ? 'Took' : 'Waiting'} {ageText(c, now)}
              </p>
              <Actions c={c} busy={busy.has(c.ref)} onChange={onChange} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
