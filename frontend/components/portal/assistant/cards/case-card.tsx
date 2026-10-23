'use client';

import { LifeBuoyIcon } from 'lucide-react';
import { caseCategoryLabel } from '@/components/portal/support/case-categories';
import { CaseStatusChip } from '@/components/portal/support/case-table';
import { IconTile } from '@/components/portal/ui/icon-tile';
import { SmallLink } from '@/components/portal/ui/link-button';
import type { TelcoCasePayload } from '@/lib/telco-topics';

/** The support case the agent just opened: ref, category, status and a link to Support. */
export function CaseCard({ data }: { data: TelcoCasePayload }) {
  return (
    <section
      aria-label={`Support case ${data.ref}`}
      className="bg-surface border-line rounded-metric flex w-full max-w-[380px] items-center gap-3 border p-3.5"
    >
      <IconTile icon={LifeBuoyIcon} tone="orange" />
      <div className="min-w-0 flex-1">
        <p className="text-muted-foreground text-[10px] font-bold">Support case created</p>
        <p className="truncate text-sm font-extrabold tracking-[-0.2px] tabular-nums">{data.ref}</p>
        <p className="text-muted-foreground truncate text-[11px]">
          {caseCategoryLabel(data.category)}
          {data.priority === 'high' && ' · High priority'}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <CaseStatusChip status={data.status} />
        <SmallLink href="/portal/support">View in Support</SmallLink>
      </div>
    </section>
  );
}
