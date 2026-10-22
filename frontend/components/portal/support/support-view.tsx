'use client';

import { useState } from 'react';
import { PlusIcon, SparklesIcon, WifiIcon } from 'lucide-react';
import { usePortalMe } from '@/components/portal/portal-me-context';
import { CaseMetrics } from '@/components/portal/support/case-metrics';
import { CaseTable } from '@/components/portal/support/case-table';
import { NewCaseDialog } from '@/components/portal/support/new-case-dialog';
import { LinkButton, PortalButton } from '@/components/portal/ui/link-button';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { formatDay } from '@/lib/telco-format';
import type { IncidentKind, IncidentView } from '@/lib/types/portal';

const KIND: Record<IncidentKind, string> = {
  outage: 'Outage',
  congestion: 'Congestion',
  maintenance: 'Maintenance',
};

function Incident({ incident }: { incident: IncidentView }) {
  const tone =
    incident.status === 'resolved'
      ? 'success'
      : incident.status === 'scheduled'
        ? 'open'
        : 'pending';
  return (
    <li className="border-line border-b py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="mb-1 flex items-center justify-between gap-2">
        <p className="text-xs font-bold">
          {KIND[incident.kind]} in {incident.area}
        </p>
        <StatusChip tone={tone}>{incident.status}</StatusChip>
      </div>
      <p className="text-muted-foreground text-[11px]">{incident.message}</p>
      <p className="text-muted-foreground mt-1 text-[10px]">
        From {formatDay(incident.starts_at)}
        {incident.ends_at && ` until ${formatDay(incident.ends_at)}`}
      </p>
    </li>
  );
}

function NetworkPanel() {
  const me = usePortalMe();
  const network = usePortalQuery('network', portalApi.network);
  return (
    <Panel>
      <PanelHeader title="Network status" description={`Known issues in ${me.district}`} />
      {network.data ? (
        network.data.length === 0 ? (
          <div className="flex items-center gap-3 py-1">
            <WifiIcon className="text-mint size-5 shrink-0" aria-hidden="true" />
            <p className="text-muted-foreground text-[11px]">No known issues in {me.district}.</p>
          </div>
        ) : (
          <ul>
            {network.data.map((i) => (
              <Incident key={`${i.area}-${i.starts_at}`} incident={i} />
            ))}
          </ul>
        )
      ) : network.error && !network.loading ? (
        <LoadError what="Network status" error={network.error} onRetry={network.reload} />
      ) : (
        <div aria-hidden="true" className="space-y-2">
          <Bone className="h-3 w-1/2" />
          <Bone className="h-2.5 w-3/4" />
        </div>
      )}
    </Panel>
  );
}

/** Support cases: counts, the request list, network status and the way to file a new case. */
export function SupportView() {
  const cases = usePortalQuery('cases', portalApi.cases);
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="phone:text-[23px] mb-[5px] text-[25px] font-bold tracking-[-0.8px]">
            Support cases
          </h1>
          <p className="text-muted-foreground text-xs">
            Track your requests and tell us when something is wrong.
          </p>
        </div>
        <PortalButton onClick={() => setDialogOpen(true)} className="shrink-0">
          <PlusIcon aria-hidden="true" />
          New case
        </PortalButton>
      </div>

      <CaseMetrics cases={cases.data} />

      <div className="tablet:grid-cols-1 grid grid-cols-[minmax(0,1.6fr)_minmax(280px,0.9fr)] items-start gap-[18px]">
        <Panel>
          <PanelHeader title="Your requests" className="mb-2" />
          {cases.data ? (
            <CaseTable cases={cases.data} />
          ) : cases.error && !cases.loading ? (
            <LoadError what="Your cases" error={cases.error} onRetry={cases.reload} />
          ) : (
            <div aria-hidden="true" className="space-y-3 py-2">
              <Bone className="h-4 w-full" />
              <Bone className="h-4 w-full" />
              <Bone className="h-4 w-2/3" />
            </div>
          )}
        </Panel>
        <div className="flex min-w-0 flex-col gap-[18px]">
          <NetworkPanel />
          <Panel>
            <PanelHeader
              title="Need help now?"
              description="telco. AI can check your account and answer straight away."
              className="mb-0"
            />
            <LinkButton href="/portal/assistant" variant="soft" className="mt-[13px]">
              <SparklesIcon aria-hidden="true" />
              Ask telco. AI
            </LinkButton>
          </Panel>
        </div>
      </div>

      <NewCaseDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
}
