import { ArrowUpRightIcon, RefreshCwIcon } from 'lucide-react';
import { LinkButton } from '@/components/portal/ui/link-button';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { nearestExpiring } from '@/lib/portal-allowances';
import { cn } from '@/lib/shadcn/utils';
import { daysUntil, formatDate, formatTaka } from '@/lib/telco-format';
import type { AccountSummary, PackageView } from '@/lib/types/portal';

function expiresIn(days: number): string {
  if (days <= 0) return 'today';
  return days === 1 ? 'tomorrow' : `in ${days} days`;
}

/** "Keep your pack active": the pack that expires first, a renew link and its auto-renew state. */
export function KeepActive({
  summary,
  packages,
  now,
}: {
  summary: AccountSummary;
  packages: PackageView[] | undefined;
  now: Date;
}) {
  const sub = nearestExpiring(summary.subscriptions);

  if (!sub) {
    return (
      <Panel>
        <PanelHeader title="Keep your pack active" description="You have no active pack." />
        <div className="bg-surface2 flex flex-wrap items-center justify-between gap-3 rounded-xl p-4">
          <p className="text-muted-foreground text-[11px]">Pick a pack for data, minutes or SMS.</p>
          <LinkButton href="/portal/packages">Buy a pack</LinkButton>
        </div>
      </Panel>
    );
  }

  const days = daysUntil(sub.expires_at, now);
  const pkg = packages?.find((p) => p.code === sub.package_code);
  const soon = days <= 3;

  return (
    <Panel>
      <PanelHeader
        title="Keep your pack active"
        description={`${sub.package_name} expires ${expiresIn(days)}.`}
      />
      <div className="bg-surface2 rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 text-sm font-bold">{sub.package_name}</p>
          <StatusChip tone={soon ? 'pending' : 'success'}>
            {soon ? 'Expiring soon' : 'Active'}
          </StatusChip>
        </div>
        <p className="text-muted-foreground mt-1.5 text-[11px]">
          {pkg && `${formatTaka(pkg.price)} · ${pkg.validity_days} days · `}
          Expires {formatDate(sub.expires_at)}
        </p>
        <p className="mt-3 flex items-center gap-2 text-[11px]">
          <RefreshCwIcon className="text-muted-foreground size-3.5" aria-hidden="true" />
          Auto-renew
          <span
            className={cn(
              'rounded-md px-[7px] py-0.5 text-[10px] font-extrabold',
              sub.auto_renew
                ? 'bg-status-success text-status-success-foreground'
                : 'bg-line text-muted-foreground'
            )}
          >
            {sub.auto_renew ? 'On' : 'Off'}
          </span>
        </p>
        <LinkButton
          href={`/portal/packages?highlight=${encodeURIComponent(sub.package_code)}`}
          className="mt-4"
        >
          Renew pack
          <ArrowUpRightIcon aria-hidden="true" />
        </LinkButton>
      </div>
    </Panel>
  );
}
