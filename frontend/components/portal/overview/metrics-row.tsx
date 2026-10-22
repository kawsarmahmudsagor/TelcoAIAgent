import { ActivityIcon, CalendarClockIcon, GiftIcon, PhoneIcon } from 'lucide-react';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import { Bone } from '@/components/portal/ui/query-states';
import { nearestExpiring } from '@/lib/portal-allowances';
import { cn } from '@/lib/shadcn/utils';
import { daysUntil, formatData, formatDay } from '@/lib/telco-format';
import type { AccountSummary, UsageBreakdown } from '@/lib/types/portal';

const METRICS_GRID = 'tablet:grid-cols-2 phone:gap-2.5 mb-5 grid grid-cols-4 gap-[18px]';

/** The big figure with its unit set small and muted beside it ("6.6 GB"). */
function Figure({ value, unit }: { value: string; unit?: string }) {
  return (
    <>
      {value}
      {unit && <span className="text-muted-foreground text-[13px] font-semibold"> {unit}</span>}
    </>
  );
}

/** The reference's small `.trend` pill, top right of a metric. */
function Pill({ warn, children }: { warn?: boolean; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        'rounded-[7px] px-[7px] py-1 text-[10px] font-extrabold whitespace-nowrap',
        warn
          ? 'bg-status-pending text-status-pending-foreground'
          : 'bg-status-success text-status-success-foreground'
      )}
    >
      {children}
    </span>
  );
}

function daysLeftText(days: number): string {
  if (days <= 0) return 'Ends today';
  return days === 1 ? '1 day left' : `${days} days left`;
}

/** Data and minutes used in 30 days, the next pack expiry and the reward points. */
export function MetricsRow({
  summary,
  usage,
  now,
}: {
  summary: AccountSummary;
  /** `usage(30)`; undefined while it loads (or if it failed). */
  usage: UsageBreakdown | undefined;
  now: Date;
}) {
  const used = (kind: 'data' | 'voice') => usage?.totals.find((t) => t.kind === kind)?.amount ?? 0;
  const [dataValue, dataUnit] = formatData(used('data')).split(' ');
  const pending = <Bone className="mt-1 h-7 w-20" />;

  const nearest = nearestExpiring(summary.subscriptions);
  const expiry = summary.nearest_expiry;
  const days = expiry ? daysUntil(expiry, now) : null;
  const [expiryDay, expiryMonth] = expiry ? formatDay(expiry).split(' ') : [];

  return (
    <div className={METRICS_GRID}>
      <MetricTile
        icon={ActivityIcon}
        tone="green"
        label="Data used"
        value={usage ? <Figure value={dataValue} unit={dataUnit} /> : pending}
        foot="Last 30 days"
      />
      <MetricTile
        icon={PhoneIcon}
        tone="purple"
        label="Minutes used"
        value={
          usage ? (
            <Figure value={Math.round(used('voice')).toLocaleString('en-IN')} unit="min" />
          ) : (
            pending
          )
        }
        foot="Last 30 days"
      />
      <MetricTile
        icon={CalendarClockIcon}
        tone="orange"
        label="Active pack expires"
        value={expiry ? <Figure value={expiryDay} unit={expiryMonth} /> : <Figure value="—" />}
        badge={days !== null && <Pill warn={days <= 3}>{daysLeftText(days)}</Pill>}
        foot={nearest ? nearest.package_name : 'No active pack'}
      />
      <MetricTile
        icon={GiftIcon}
        tone="pink"
        label="Telco rewards"
        value={<Figure value={summary.reward_points.toLocaleString('en-IN')} unit="pts" />}
        foot="Redeem them in Offers & rewards"
      />
    </div>
  );
}

export function MetricsRowSkeleton() {
  return (
    <div className={METRICS_GRID} aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="bg-surface border-line rounded-metric phone:p-3.5 flex flex-col gap-3 border p-[18px]"
        >
          <Bone className="size-9 rounded-[11px]" />
          <Bone className="h-3 w-20" />
          <Bone className="h-7 w-24" />
        </div>
      ))}
    </div>
  );
}
