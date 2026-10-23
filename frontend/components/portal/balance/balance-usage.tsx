'use client';

import { useState } from 'react';
import { DetailCards, DetailCardsSkeleton } from '@/components/portal/balance/detail-cards';
import { KeepActive } from '@/components/portal/balance/keep-active';
import { UsageBreakdown } from '@/components/portal/balance/usage-breakdown';
import { Panel } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';

/** The Balance & usage page: balance and allowance cards, the usage breakdown, the renew box. */
export function BalanceUsage() {
  const [now] = useState(() => new Date());
  const summary = usePortalQuery('summary', portalApi.summary);
  const packages = usePortalQuery('packages', () => portalApi.packages());

  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] mb-[5px] text-[25px] font-bold tracking-[-0.8px]">
          Balance &amp; usage
        </h1>
        <p className="text-muted-foreground text-xs">
          Know where your balance goes and keep track of every allowance.
        </p>
      </div>

      {summary.data ? (
        <DetailCards summary={summary.data} packages={packages.data} />
      ) : summary.error && !summary.loading ? (
        <Panel>
          <LoadError what="Your balance" error={summary.error} onRetry={summary.reload} />
        </Panel>
      ) : (
        <DetailCardsSkeleton />
      )}

      <div className="phone:grid-cols-1 mt-[18px] grid grid-cols-[minmax(0,1.35fr)_minmax(280px,1fr)] gap-[18px]">
        <UsageBreakdown />
        {summary.data ? (
          <KeepActive summary={summary.data} packages={packages.data} now={now} />
        ) : summary.error ? null : (
          <Panel aria-hidden="true" className="flex flex-col gap-3">
            <Bone className="h-4 w-40" />
            <Bone className="h-3 w-56" />
            <Bone className="h-32 w-full rounded-xl" />
          </Panel>
        )}
      </div>
    </>
  );
}
