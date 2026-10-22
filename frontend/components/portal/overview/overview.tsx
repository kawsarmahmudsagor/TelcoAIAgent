'use client';

import { useState } from 'react';
import { CalendarDaysIcon } from 'lucide-react';
import {
  AllowancesCard,
  AllowancesCardSkeleton,
} from '@/components/portal/overview/allowances-card';
import { BalanceHero, BalanceHeroSkeleton } from '@/components/portal/overview/balance-hero';
import { MadeForYou } from '@/components/portal/overview/made-for-you';
import { MetricsRow, MetricsRowSkeleton } from '@/components/portal/overview/metrics-row';
import { QuickActions } from '@/components/portal/overview/quick-actions';
import { RecentActivity } from '@/components/portal/overview/recent-activity';
import { UsageChart } from '@/components/portal/overview/usage-chart';
import { usePortalMe } from '@/components/portal/portal-me-context';
import { Panel } from '@/components/portal/ui/panel';
import { LoadError } from '@/components/portal/ui/query-states';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { formatLongDate, greeting } from '@/lib/telco-format';

const HERO_GRID =
  'phone:grid-cols-1 mb-[18px] grid grid-cols-[minmax(0,1.5fr)_minmax(270px,1fr)] gap-[18px]';

/** The Overview page: greeting, balance and allowances, metrics, shortcuts, usage, activity, offers. */
export function Overview() {
  const me = usePortalMe();
  // Read once per visit: the greeting and the "days left" count don't need to tick.
  const [now] = useState(() => new Date());
  const summary = usePortalQuery('summary', portalApi.summary);
  const packages = usePortalQuery('packages', () => portalApi.packages());
  const usage30 = usePortalQuery('usage', () => portalApi.usage(30), 30);

  return (
    <>
      <div className="phone:flex-col phone:items-start mb-6 flex items-end justify-between gap-[18px]">
        <div className="min-w-0">
          <h1 className="phone:text-[23px] mb-[5px] text-[26px] font-bold tracking-[-1px]">
            {greeting(now)}, {me.first_name}
          </h1>
          <p className="text-muted-foreground text-[13px]">
            Here’s what’s happening with your Telco number today.
          </p>
        </div>
        <p className="border-line bg-surface text-muted-foreground rounded-button phone:hidden flex items-center gap-[7px] border px-3 py-[9px] text-xs whitespace-nowrap">
          <CalendarDaysIcon className="size-3.5" aria-hidden="true" />
          {formatLongDate(now)}
        </p>
      </div>

      <section aria-label="Your account">
        {summary.data ? (
          <>
            <div className={HERO_GRID}>
              <BalanceHero summary={summary.data} />
              <AllowancesCard summary={summary.data} packages={packages.data} />
            </div>
            <MetricsRow
              summary={summary.data}
              usage={usage30.data}
              usageFailed={usage30.error !== undefined}
              now={now}
            />
          </>
        ) : summary.error && !summary.loading ? (
          <Panel className="mb-5">
            <LoadError what="Your account" error={summary.error} onRetry={summary.reload} />
          </Panel>
        ) : (
          <>
            <div className={HERO_GRID}>
              <BalanceHeroSkeleton />
              <AllowancesCardSkeleton />
            </div>
            <MetricsRowSkeleton />
          </>
        )}
      </section>

      <QuickActions />

      <div className="phone:grid-cols-1 grid grid-cols-[minmax(0,1.35fr)_minmax(280px,1fr)] gap-[18px]">
        <UsageChart />
        <RecentActivity />
      </div>

      <MadeForYou />
    </>
  );
}
