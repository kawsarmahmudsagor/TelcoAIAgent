'use client';

import {
  AlertTriangleIcon,
  BanknoteIcon,
  CheckCircle2Icon,
  LifeBuoyIcon,
  SparklesIcon,
  UsersIcon,
} from 'lucide-react';
import { ActivityChart } from '@/components/dashboard/control/activity-chart';
import { AttentionPanel } from '@/components/dashboard/control/attention-panel';
import { HealthPanel } from '@/components/dashboard/control/health-panel';
import { RunNudgesButton } from '@/components/dashboard/control/run-nudges-button';
import { KbStatusPanel } from '@/components/dashboard/overview/kb-status-panel';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { SectionHead } from '@/components/portal/ui/section-head';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { adminApi } from '@/lib/admin-api';
import { useAdminQuery } from '@/lib/admin-query';
import { formatTaka } from '@/lib/telco-format';
import type { Overview } from '@/lib/types/admin';

const nf = new Intl.NumberFormat('en-IN');

export function ControlCenter() {
  const { data, error, loading, reload } = useAdminQuery('overview', () => adminApi.overview());
  const needsAttention = data?.attention.some((a) => a.severity === 'high') ?? false;

  return (
    <>
      <section className="rounded-hero from-brand to-brand2 phone:p-[19px] shadow-panel relative flex flex-wrap items-center justify-between gap-4 bg-linear-[115deg] px-[27px] py-[25px] text-white">
        <div className="min-w-0">
          <h1 className="phone:text-[22px] text-[26px] font-extrabold tracking-[-0.8px]">
            Operations control center
          </h1>
          <p className="mt-1 text-xs text-white/80">Live overview of the telco. environment.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {data && (
            <p
              role="status"
              className="rounded-button flex min-h-9 items-center gap-[7px] border border-white/25 bg-white/10 px-3.5 text-xs font-bold"
            >
              {needsAttention ? (
                <AlertTriangleIcon className="size-3.5" aria-hidden="true" />
              ) : (
                <CheckCircle2Icon className="size-3.5" aria-hidden="true" />
              )}
              {needsAttention ? 'Needs attention' : 'All systems operational'}
            </p>
          )}
          <RunNudgesButton />
        </div>
      </section>

      {error && !data ? (
        <Panel className="mt-4">
          <LoadError what="The overview" error={error} onRetry={reload} />
        </Panel>
      ) : (
        <Body data={data} loading={loading} />
      )}

      <SectionHead
        title="Knowledge base"
        description="Whether the agent can answer from your sources."
      />
      <KbStatusPanel className="rounded-panel! shadow-panel" />
    </>
  );
}

function Body({ data, loading }: { data?: Overview; loading: boolean }) {
  const o = data;
  return (
    <>
      <div className="tablet:grid-cols-2 mt-4 grid grid-cols-4 gap-4">
        <MetricTile
          icon={UsersIcon}
          tone="purple"
          label="Total subscribers"
          value={o ? nf.format(o.subscribers.total) : <Bone className="h-7 w-20" />}
          foot={
            o &&
            `${nf.format(o.subscribers.prepaid)} prepaid · ${nf.format(o.subscribers.postpaid)} postpaid`
          }
        />
        <MetricTile
          icon={BanknoteIcon}
          tone="green"
          label="Recharge volume today"
          value={o ? formatTaka(o.recharge_today.amount) : <Bone className="h-7 w-24" />}
          foot={
            o &&
            `${nf.format(o.recharge_today.count)} successful ${o.recharge_today.count === 1 ? 'recharge' : 'recharges'}`
          }
        />
        <MetricTile
          icon={LifeBuoyIcon}
          tone="orange"
          label="Support cases"
          value={o ? nf.format(o.cases.open) : <Bone className="h-7 w-12" />}
          badge={
            o && o.cases.open > 0 && <StatusChip tone="pending">{o.cases.open} open</StatusChip>
          }
          foot={o && `${o.cases.high_open} high priority`}
        />
        <MetricTile
          icon={SparklesIcon}
          tone="green"
          label="AI resolution rate"
          value={
            o ? `${Math.round(o.ai.resolution_rate * 1000) / 10}%` : <Bone className="h-7 w-16" />
          }
          foot={
            o &&
            `Last 24 hours · ${nf.format(o.ai.chats_24h)} ${o.ai.chats_24h === 1 ? 'chat' : 'chats'}`
          }
        />
      </div>

      <div className="tablet:grid-cols-1 mt-4 grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-4">
        <Panel aria-busy={loading && !o}>
          <PanelHeader
            title="Service activity — last 7 days"
            description="Recharge value and new cases per day"
          />
          {o ? <ActivityChart points={o.activity} /> : <Bone className="h-64 w-full" />}
        </Panel>
        {o ? (
          <HealthPanel health={o.health} />
        ) : (
          <Panel>
            <PanelHeader title="Platform health" description="Key service indicators" />
            <Bone className="h-40 w-full" />
          </Panel>
        )}
      </div>

      <SectionHead title="Needs attention" description="Raised by the monitoring rules." />
      {o ? (
        <AttentionPanel items={o.attention} />
      ) : (
        <Panel>
          <Bone className="h-16 w-full" />
        </Panel>
      )}
    </>
  );
}
