'use client';

import { LayersIcon, MessageSquareTextIcon, PhoneIcon, WifiIcon } from 'lucide-react';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { formatData, formatTaka } from '@/lib/telco-format';
import type { UsageKind } from '@/lib/types/portal';

const ROWS: Record<
  UsageKind,
  { icon: typeof WifiIcon; label: string; line: string; amount(n: number): string }
> = {
  data: {
    icon: WifiIcon,
    label: 'Mobile internet',
    line: 'Video, browsing and apps',
    amount: formatData,
  },
  voice: {
    icon: PhoneIcon,
    label: 'Voice calls',
    line: 'Outgoing local calls',
    amount: (n) => `${Math.round(n).toLocaleString('en-IN')} min`,
  },
  sms: {
    icon: MessageSquareTextIcon,
    label: 'SMS',
    line: 'Local messages',
    amount: (n) => `${Math.round(n).toLocaleString('en-IN')} SMS`,
  },
  vas: {
    icon: LayersIcon,
    label: 'Value-added services',
    line: 'Subscriptions and content',
    amount: (n) => (n === 1 ? '1 service' : `${Math.round(n)} services`),
  },
};

const ORDER: UsageKind[] = ['data', 'voice', 'sms', 'vas'];

/** "Usage breakdown": data, voice, SMS and VAS used in the last 30 days, with what was charged. */
export function UsageBreakdown() {
  const query = usePortalQuery('usage', () => portalApi.usage(30), 30);
  const usage = query.data;
  const totals = usage ? ORDER.flatMap((kind) => usage.totals.filter((t) => t.kind === kind)) : [];

  return (
    <Panel>
      <PanelHeader title="Usage breakdown" description="Last 30 days" className="mb-3" />
      {usage ? (
        totals.length === 0 ? (
          <p className="text-muted-foreground py-2 text-sm">No usage in the last 30 days.</p>
        ) : (
          <ul>
            {totals.map((t) => {
              const row = ROWS[t.kind];
              const Icon = row.icon;
              return (
                <li
                  key={t.kind}
                  className="border-line flex items-center gap-[11px] border-b py-[13px] last:border-b-0 last:pb-0"
                >
                  <span
                    aria-hidden="true"
                    className="bg-surface2 grid size-9 shrink-0 place-items-center rounded-[11px] [&_svg]:size-4"
                  >
                    <Icon />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[11px] font-bold">{row.label}</p>
                    <p className="text-muted-foreground truncate text-[10px]">{row.line}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-xs font-extrabold whitespace-nowrap">
                      {row.amount(t.amount)}
                    </p>
                    <p className="text-muted-foreground text-[10px] whitespace-nowrap">
                      {t.charge > 0 ? `${formatTaka(t.charge)} charged` : 'No charge'}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )
      ) : query.error && !query.loading ? (
        <LoadError what="Your usage" error={query.error} onRetry={query.reload} />
      ) : (
        <ul aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <li key={i} className="flex items-center gap-[11px] py-[13px]">
              <Bone className="size-9 rounded-[11px]" />
              <div className="flex-1 space-y-2">
                <Bone className="h-3 w-1/2" />
                <Bone className="h-2.5 w-1/3" />
              </div>
              <Bone className="h-4 w-14" />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
