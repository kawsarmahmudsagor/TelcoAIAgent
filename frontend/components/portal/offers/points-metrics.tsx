import { GiftIcon, TagIcon, TrophyIcon } from 'lucide-react';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import type { OffersAndPoints } from '@/lib/types/portal';

export const METRICS_GRID = 'phone:grid-cols-1 phone:gap-2.5 mb-5 grid grid-cols-3 gap-[18px]';

const pts = (n: number) => n.toLocaleString('en-IN');

/** Points, how many offers there are, and how far the cheapest points offer is. */
export function PointsMetrics({ data }: { data: OffersAndPoints }) {
  const { reward_points: points, offers } = data;
  const costs = offers.flatMap((o) => (o.points_cost !== null ? [o.points_cost] : []));
  const cheapest = costs.length > 0 ? Math.min(...costs) : null;
  const short = cheapest !== null ? Math.max(0, cheapest - points) : null;

  return (
    <div className={METRICS_GRID}>
      <MetricTile
        icon={GiftIcon}
        tone="purple"
        label="telco reward points"
        value={
          <>
            {pts(points)}
            <span className="text-muted-foreground text-[13px] font-semibold"> pts</span>
          </>
        }
        foot="Earned on recharges and packs"
      />
      <MetricTile
        icon={TagIcon}
        tone="orange"
        label="Offers for you"
        value={offers.length}
        foot="Picked for your number"
      />
      <MetricTile
        icon={TrophyIcon}
        tone="green"
        label="Next reward"
        value={
          cheapest === null ? (
            '—'
          ) : (
            <>
              {pts(cheapest)}
              <span className="text-muted-foreground text-[13px] font-semibold"> pts</span>
            </>
          )
        }
        foot={
          cheapest === null
            ? 'No points offers right now'
            : short === 0
              ? 'Enough for a reward'
              : `${pts(short ?? 0)} points to your next reward`
        }
      />
    </div>
  );
}
