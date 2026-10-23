import { PersonCell } from '@/components/dashboard/person-cell';
import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import { formatDayTime, humanize } from '@/lib/telco-format';
import type { AuditItem } from '@/lib/types/admin';

const ACTOR: Record<string, { tone: StatusTone; label: string }> = {
  agent: { tone: 'open', label: 'Assistant' },
  portal: { tone: 'success', label: 'Subscriber' },
  admin: { tone: 'pending', label: 'Admin' },
  system: { tone: 'open', label: 'System' },
};

function ActorChip({ actor }: { actor: string }) {
  const a = ACTOR[actor] ?? { tone: 'open' as const, label: humanize(actor) };
  return <StatusChip tone={a.tone}>{a.label}</StatusChip>;
}

function Subject({ a }: { a: AuditItem }) {
  if (!a.subscriber_name) return <span className="text-muted-foreground">—</span>;
  return <PersonCell name={a.subscriber_name} msisdn={a.msisdn_masked ?? ''} />;
}

/** Newest first. A table, or stacked cards at 1100px and below. */
export function AuditTable({ items }: { items: AuditItem[] }) {
  return (
    <>
      <table className="tablet:hidden w-full border-collapse text-left">
        <caption className="sr-only">Audit trail, newest first</caption>
        <thead>
          <tr className="text-muted-foreground border-line border-b text-[11px]">
            {['Time', 'Actor', 'Action', 'Subscriber', 'Detail'].map((h) => (
              <th key={h} scope="col" className="py-2.5 pr-3 font-semibold whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((a, i) => (
            <tr key={i} className="border-line border-b align-top text-xs last:border-b-0">
              <td className="py-3 pr-3 whitespace-nowrap">{formatDayTime(a.created_at)}</td>
              <td className="py-3 pr-3">
                <ActorChip actor={a.actor} />
              </td>
              <td className="py-3 pr-3 font-bold whitespace-nowrap">{humanize(a.action)}</td>
              <td className="max-w-[220px] py-3 pr-3">
                <Subject a={a} />
              </td>
              <td className="text-muted-foreground max-w-[320px] py-3 text-[11px] break-words">
                {a.detail || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="tablet:block hidden">
        {items.map((a, i) => (
          <li key={i} className="border-line border-b py-3.5 first:pt-0 last:border-b-0 last:pb-0">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <p className="text-xs font-bold">{humanize(a.action)}</p>
              <ActorChip actor={a.actor} />
            </div>
            {a.subscriber_name && (
              <div className="mb-1.5">
                <Subject a={a} />
              </div>
            )}
            {a.detail && (
              <p className="text-muted-foreground text-[11px] break-words">{a.detail}</p>
            )}
            <p className="text-muted-foreground mt-1 text-[10px]">{formatDayTime(a.created_at)}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
