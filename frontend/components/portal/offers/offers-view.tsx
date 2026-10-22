'use client';

import { useState } from 'react';
import { GiftIcon } from 'lucide-react';
import { usePortalAction } from '@/components/portal/actions/use-portal-action';
import { OfferCard } from '@/components/portal/offers/offer-card';
import { METRICS_GRID, PointsMetrics } from '@/components/portal/offers/points-metrics';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { StatusChip } from '@/components/portal/ui/status-chip';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { formatDate } from '@/lib/telco-format';

const GRID = 'tablet:grid-cols-2 phone:grid-cols-1 grid grid-cols-3 gap-[18px]';

/** Offers & rewards: points metrics, the offer cards and the reward activity list. */
export function OffersView() {
  const offers = usePortalQuery('offers', portalApi.offers);
  const data = offers.data;
  const { start, dialog } = usePortalAction();
  const [redeeming, setRedeeming] = useState<string | null>(null);

  async function redeem(offerId: string) {
    if (redeeming) return;
    setRedeeming(offerId);
    await start({ kind: 'redeem', offer_id: offerId });
    setRedeeming(null);
  }

  return (
    <>
      {data ? (
        <>
          <PointsMetrics data={data} />
          {data.offers.length === 0 ? (
            <Panel>
              <p className="text-muted-foreground text-sm">
                No offers on your number right now. New ones appear here first.
              </p>
            </Panel>
          ) : (
            <ul className={GRID}>
              {data.offers.map((offer) => (
                <OfferCard
                  key={offer.id}
                  offer={offer}
                  points={data.reward_points}
                  redeeming={redeeming === offer.id}
                  onRedeem={() => void redeem(offer.id)}
                />
              ))}
            </ul>
          )}
        </>
      ) : offers.error && !offers.loading ? (
        <Panel>
          <LoadError what="Your offers" error={offers.error} onRetry={offers.reload} />
        </Panel>
      ) : (
        <div aria-hidden="true">
          <div className={METRICS_GRID}>
            {[0, 1, 2].map((i) => (
              <Bone key={i} className="rounded-metric h-[132px]" />
            ))}
          </div>
          <div className={GRID}>
            {[0, 1, 2].map((i) => (
              <Bone key={i} className="rounded-metric h-[190px]" />
            ))}
          </div>
        </div>
      )}

      <RewardActivity />
      {dialog}
    </>
  );
}

/** "Your reward activity": the customer's redemptions. */
function RewardActivity() {
  const txns = usePortalQuery('transactions', () => portalApi.transactions({ type: 'redeem' }), {
    type: 'redeem',
  });

  return (
    <Panel className="mt-[18px]">
      <PanelHeader title="Your reward activity" className="mb-2" />
      {txns.data ? (
        txns.data.length === 0 ? (
          <p className="text-muted-foreground py-3 text-[11px]">
            No redemptions yet. Redeem an offer above with your points.
          </p>
        ) : (
          <ul>
            {txns.data.map((txn) => (
              <li
                key={txn.ref}
                className="border-line flex items-center gap-[11px] border-b py-[13px] last:border-b-0 last:pb-0"
              >
                <span
                  aria-hidden="true"
                  className="bg-tint-green text-mint grid size-9 shrink-0 place-items-center rounded-[11px] [&_svg]:size-4"
                >
                  <GiftIcon />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] font-bold">
                    {txn.package_name ? `${txn.package_name} redeemed` : 'Reward redeemed'}
                  </p>
                  <p className="text-muted-foreground truncate text-[10px]">
                    {formatDate(txn.created_at)} · {txn.ref}
                  </p>
                </div>
                <StatusChip tone={txn.status}>{txn.status}</StatusChip>
              </li>
            ))}
          </ul>
        )
      ) : txns.error && !txns.loading ? (
        <LoadError what="Your reward activity" error={txns.error} onRetry={txns.reload} />
      ) : (
        <ul aria-hidden="true">
          {[0, 1].map((i) => (
            <li key={i} className="flex items-center gap-[11px] py-[13px]">
              <Bone className="size-9 rounded-[11px]" />
              <div className="flex-1 space-y-2">
                <Bone className="h-3 w-1/2" />
                <Bone className="h-2.5 w-1/3" />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
