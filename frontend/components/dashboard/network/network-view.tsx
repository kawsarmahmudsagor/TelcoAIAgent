'use client';

import { useState } from 'react';
import {
  CheckCircle2Icon,
  MapPinIcon,
  PlusIcon,
  RadioTowerIcon,
  TriangleAlertIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  HealthChip,
  IncidentStatusChip,
  KIND_LABEL,
  isLive,
} from '@/components/dashboard/network/incident-parts';
import { StageIncidentDialog } from '@/components/dashboard/network/stage-incident-dialog';
import { PortalButton } from '@/components/portal/ui/link-button';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { adminApi } from '@/lib/admin-api';
import { invalidateAdmin, useAdminQuery } from '@/lib/admin-query';
import { cn } from '@/lib/shadcn/utils';
import { formatDayTime } from '@/lib/telco-format';
import type { IncidentAdminView } from '@/lib/types/admin';

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function when(i: IncidentAdminView): string {
  const from = formatDayTime(i.starts_at);
  return i.ends_at ? `${from} to ${formatDayTime(i.ends_at)}` : `Since ${from}`;
}

export function NetworkView() {
  const { data, error, reload } = useAdminQuery('network', adminApi.network);
  const [staging, setStaging] = useState(false);
  const [resolving, setResolving] = useState<string | null>(null);

  const now = new Date();
  const live = data?.incidents.filter((i) => isLive(i, now)) ?? [];
  const past = data?.incidents.filter((i) => !isLive(i, now)) ?? [];
  const degraded = data?.districts.filter((d) => d.health === 'degraded').length ?? 0;
  const scheduled = live.filter((i) => i.status === 'scheduled').length;

  async function resolve(i: IncidentAdminView) {
    setResolving(i.id);
    try {
      await adminApi.resolveIncident(i.id);
      toast.success(`${i.area} resolved`, { description: 'Subscribers no longer see it.' });
      invalidateAdmin(['network', 'overview']);
    } catch (err) {
      toast.error(`Could not resolve ${i.area}`, {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setResolving(null);
    }
  }

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="phone:text-[23px] text-[25px] font-bold tracking-[-0.8px]">
            Network status
          </h1>
          <p className="text-muted-foreground mt-1 text-xs">
            Regional service health and the incidents subscribers and the assistant are told about.
          </p>
        </div>
        <PortalButton onClick={() => setStaging(true)} disabled={!data}>
          <PlusIcon aria-hidden="true" />
          Stage incident
        </PortalButton>
      </div>

      {error && !data ? (
        <Panel>
          <LoadError what="Network status" error={error} onRetry={reload} />
        </Panel>
      ) : (
        <>
          <section
            aria-label="Overall status"
            className={cn(
              'rounded-panel mb-4 flex items-center gap-3.5 border p-[18px]',
              !data || degraded === 0
                ? 'bg-tint-green border-mint/30'
                : 'bg-tint-orange border-orange/40'
            )}
          >
            {data && degraded > 0 ? (
              <TriangleAlertIcon className="text-orange size-6 shrink-0" aria-hidden="true" />
            ) : (
              <CheckCircle2Icon className="text-mint size-6 shrink-0" aria-hidden="true" />
            )}
            <div className="min-w-0" aria-live="polite">
              <h2 className="text-base font-extrabold tracking-[-0.3px]">
                {!data
                  ? 'Checking the network…'
                  : degraded === 0
                    ? 'Network operating normally'
                    : `Service degraded in ${plural(degraded, 'district', 'districts')}`}
              </h2>
              <p className="text-muted-foreground mt-0.5 text-xs">
                {data && degraded > 0
                  ? 'Affected subscribers are told about it when they ask the assistant.'
                  : 'No district has a service-affecting incident in force.'}
              </p>
            </div>
          </section>

          <div className="phone:grid-cols-1 mb-4 grid grid-cols-3 gap-4">
            <MetricTile
              icon={RadioTowerIcon}
              tone="orange"
              label="Active incidents"
              value={data ? live.length : <Bone className="h-7 w-10" />}
              foot={data && (scheduled > 0 ? `${scheduled} scheduled` : 'None scheduled')}
            />
            <MetricTile
              icon={MapPinIcon}
              tone="purple"
              label="Districts monitored"
              value={data ? data.districts.length : <Bone className="h-7 w-10" />}
              foot={data && 'Where subscribers or incidents are'}
            />
            <MetricTile
              icon={TriangleAlertIcon}
              tone="pink"
              label="Districts degraded"
              value={data ? degraded : <Bone className="h-7 w-10" />}
              foot={data && 'Outage or congestion in force'}
            />
          </div>

          <div className="tablet:grid-cols-1 grid grid-cols-2 gap-4">
            <Panel>
              <PanelHeader title="Regional service health" description="By district" />
              {!data ? (
                <div className="space-y-3" aria-busy="true">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Bone key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : data.districts.length === 0 ? (
                <p className="text-muted-foreground text-xs">No districts to monitor yet.</p>
              ) : (
                <ul>
                  {data.districts.map((d) => (
                    <li
                      key={d.district}
                      className="border-line flex items-center justify-between gap-3 border-b py-2.5 first:pt-0 last:border-b-0 last:pb-0"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-bold">{d.district}</p>
                        <p className="text-muted-foreground text-[11px]">
                          {d.incidents === 0
                            ? 'No incidents'
                            : plural(d.incidents, 'incident', 'incidents')}
                        </p>
                      </div>
                      <HealthChip health={d.health} />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel>
              <PanelHeader
                title="Active incidents"
                description="Resolve one when service is back"
              />
              {!data ? (
                <Bone className="h-20 w-full" />
              ) : live.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                  Nothing in force. Stage an incident to test what subscribers see.
                </p>
              ) : (
                <ul>
                  {live.map((i) => (
                    <li
                      key={i.id}
                      className="border-line flex items-start gap-3 border-b py-3 first:pt-0 last:border-b-0 last:pb-0"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-bold">
                          {KIND_LABEL[i.kind] ?? i.kind} · {i.district}, {i.area}
                        </p>
                        <p className="text-muted-foreground mt-0.5 text-[11px]">{i.message}</p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                          <IncidentStatusChip status={i.status} />
                          <span className="text-muted-foreground text-[10px]">{when(i)}</span>
                        </div>
                      </div>
                      <PortalButton
                        variant="soft"
                        disabled={resolving === i.id}
                        onClick={() => void resolve(i)}
                        aria-label={`Resolve ${i.kind} in ${i.area}, ${i.district}`}
                      >
                        {resolving === i.id ? 'Resolving…' : 'Resolve'}
                      </PortalButton>
                    </li>
                  ))}
                </ul>
              )}
              {past.length > 0 && (
                <div className="border-line mt-4 border-t pt-3">
                  <h4 className="text-muted-foreground mb-2 text-[11px] font-bold">
                    Recently ended
                  </h4>
                  <ul className="space-y-1.5">
                    {past.map((i) => (
                      <li
                        key={i.id}
                        className="text-muted-foreground flex justify-between gap-3 text-[11px]"
                      >
                        <span className="min-w-0 truncate">
                          {KIND_LABEL[i.kind] ?? i.kind} · {i.district}, {i.area}
                        </span>
                        <span className="shrink-0">
                          {i.ends_at ? formatDayTime(i.ends_at) : 'Resolved'}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Panel>
          </div>
        </>
      )}

      {data && (
        <StageIncidentDialog
          open={staging}
          onOpenChange={setStaging}
          districts={data.districts.map((d) => d.district)}
        />
      )}
    </>
  );
}
