import Link from 'next/link';
import { AlertTriangleIcon, CheckCircle2Icon, ChevronRightIcon } from 'lucide-react';
import { IconTile } from '@/components/portal/ui/icon-tile';
import { Panel } from '@/components/portal/ui/panel';
import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import type { AttentionItem } from '@/lib/types/admin';

const SEVERITY: Record<string, { tone: StatusTone; label: string }> = {
  high: { tone: 'failed', label: 'High' },
  investigate: { tone: 'pending', label: 'Investigate' },
  review: { tone: 'pending', label: 'Review' },
};

/** What the monitoring rules flagged, each linking to the page that deals with it. */
export function AttentionPanel({ items }: { items: AttentionItem[] }) {
  if (items.length === 0) {
    return (
      <Panel className="flex items-center gap-3">
        <IconTile icon={CheckCircle2Icon} tone="green" size="lg" />
        <p className="text-muted-foreground text-xs">Nothing needs attention right now.</p>
      </Panel>
    );
  }
  return (
    <Panel className="py-2.5">
      <ul>
        {items.map((item) => {
          const sev = SEVERITY[item.severity] ?? { tone: 'open' as const, label: item.severity };
          return (
            <li key={`${item.kind}:${item.title}`} className="border-line border-b last:border-b-0">
              <Link
                href={item.href}
                className="hover:bg-surface2 focus-visible:ring-ring/60 -mx-2 flex items-center gap-3 rounded-xl px-2 py-3 outline-none focus-visible:ring-[3px]"
              >
                <IconTile
                  icon={AlertTriangleIcon}
                  tone={item.severity === 'high' ? 'pink' : 'orange'}
                  size="lg"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-bold">{item.title}</span>
                  <span className="text-muted-foreground block text-[11px]">{item.detail}</span>
                </span>
                <StatusChip tone={sev.tone}>{sev.label}</StatusChip>
                <ChevronRightIcon
                  className="text-muted-foreground phone:hidden size-4 shrink-0"
                  aria-hidden="true"
                />
              </Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
