'use client';

import { useState } from 'react';
import { PencilIcon, PlusIcon, TagIcon, Trash2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { SegmentedFilter } from '@/components/dashboard/list-controls';
import { OfferDialog } from '@/components/dashboard/offers/offer-dialog';
import {
  AudienceChip,
  KINDS,
  KIND_LABEL,
  KindChip,
  validityText,
  valueText,
} from '@/components/dashboard/offers/offer-parts';
import { useUrlParams } from '@/components/dashboard/use-url-param';
import { PortalButton } from '@/components/portal/ui/link-button';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { Switch } from '@/components/ui/switch';
import { adminApi } from '@/lib/admin-api';
import { invalidateAdmin, useAdminQuery } from '@/lib/admin-query';
import { ApiError } from '@/lib/api-client';
import { cn } from '@/lib/shadcn/utils';
import type { AdminOffer, OfferKind } from '@/lib/types/admin';

type KindFilter = OfferKind | 'all';
const FILTERS: { value: KindFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  ...KINDS.map((k) => ({ value: k, label: KIND_LABEL[k] })),
];

const IN_USE = 'This offer has redemptions — deactivate it instead.';

export function OffersView() {
  const [params, setParams] = useUrlParams();
  const kind = KINDS.find((k) => k === params.get('kind'));
  const offers = useAdminQuery('offers', adminApi.offers);
  const packages = useAdminQuery('packages', adminApi.packages);

  // `undefined`: closed; `null`: creating; an offer: editing it.
  const [editing, setEditing] = useState<AdminOffer | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<AdminOffer | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [toggling, setToggling] = useState<ReadonlySet<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);

  const all = offers.data;
  const items = all?.filter((o) => !kind || o.kind === kind);

  async function toggle(o: AdminOffer, is_active: boolean) {
    setNotice(null);
    setToggling((s) => new Set(s).add(o.id));
    try {
      await adminApi.updateOffer(o.id, { is_active });
      toast.success(is_active ? `${o.title} is active` : `${o.title} is inactive`);
      invalidateAdmin(['offers']);
    } catch (err) {
      toast.error(`Could not update ${o.title}`, {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setToggling((s) => {
        const next = new Set(s);
        next.delete(o.id);
        return next;
      });
    }
  }

  async function remove() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await adminApi.deleteOffer(deleting.id);
      toast.success('Offer deleted', { description: deleting.title });
      invalidateAdmin(['offers']);
      setDeleting(null);
    } catch (err) {
      setNotice(
        err instanceof ApiError && (err.status === 409 || err.code === 'offer_in_use')
          ? IN_USE
          : err instanceof Error
            ? err.message
            : 'Could not delete the offer.'
      );
      setDeleting(null);
      invalidateAdmin(['offers']);
    } finally {
      setDeleteBusy(false);
    }
  }

  function actions(o: AdminOffer) {
    return (
      <div className="flex items-center justify-end gap-2">
        <PortalButton
          variant="outline"
          onClick={() => setEditing(o)}
          aria-label={`Edit ${o.title}`}
        >
          <PencilIcon aria-hidden="true" /> Edit
        </PortalButton>
        <PortalButton
          variant="outline"
          onClick={() => {
            setNotice(null);
            setDeleting(o);
          }}
          aria-label={`Delete ${o.title}`}
        >
          <Trash2Icon aria-hidden="true" />
        </PortalButton>
      </div>
    );
  }

  function activeSwitch(o: AdminOffer) {
    return (
      <Switch
        checked={o.is_active}
        disabled={toggling.has(o.id)}
        onCheckedChange={(v) => void toggle(o, v)}
        aria-label={`${o.title} active`}
      />
    );
  }

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="phone:text-[23px] text-[25px] font-bold tracking-[-0.8px]">Offers</h1>
          <p className="text-muted-foreground mt-1 text-xs">
            Packs, points rewards and cashback that subscribers see on their Offers page.
          </p>
        </div>
        <PortalButton onClick={() => setEditing(null)} disabled={!packages.data}>
          <PlusIcon aria-hidden="true" /> New offer
        </PortalButton>
      </div>

      {notice && (
        <p
          role="alert"
          className="bg-tint-pink text-red rounded-button mb-4 px-3.5 py-2.5 text-xs font-bold"
        >
          {notice}
        </p>
      )}

      <Panel>
        <PanelHeader
          title="All offers"
          description={
            all
              ? `${all.length} ${all.length === 1 ? 'offer' : 'offers'}${kind ? `, ${items?.length ?? 0} of them ${KIND_LABEL[kind].toLowerCase()}` : ''}`
              : 'Loading…'
          }
          action={
            <SegmentedFilter<KindFilter>
              label="Kind"
              value={kind ?? 'all'}
              options={FILTERS}
              onChange={(v) => setParams({ kind: v === 'all' ? null : v })}
            />
          }
          className="tablet:flex-col tablet:items-stretch"
        />

        {offers.error && !all ? (
          <LoadError what="Offers" error={offers.error} onRetry={offers.reload} />
        ) : !items ? (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 4 }).map((_, i) => (
              <Bone key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="text-muted-foreground flex flex-col items-center gap-2 py-10 text-center text-xs">
            <TagIcon className="size-6" aria-hidden="true" />
            <p>
              {kind
                ? `No ${KIND_LABEL[kind].toLowerCase()} offers. Pick another kind or create one.`
                : 'No offers yet. Create one to show on subscribers’ Offers page.'}
            </p>
          </div>
        ) : (
          <div
            className={cn(offers.loading && 'opacity-60 motion-safe:transition-opacity')}
            aria-busy={offers.loading}
          >
            <table className="tablet:hidden w-full border-collapse text-left">
              <caption className="sr-only">Offers, newest first</caption>
              <thead>
                <tr className="text-muted-foreground border-line border-b text-[11px]">
                  {['Offer', 'Kind', 'Audience', 'Runs', 'Redeemed', 'Active'].map((h) => (
                    <th key={h} scope="col" className="py-2.5 pr-3 font-semibold whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                  <th scope="col" className="py-2.5">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((o) => (
                  <tr key={o.id} className="border-line border-b align-top text-xs last:border-b-0">
                    <th scope="row" className="max-w-[300px] py-3 pr-3 text-left">
                      <p className="truncate font-bold">{o.title}</p>
                      <p className="text-muted-foreground truncate text-[11px] font-normal">
                        {valueText(o)}
                      </p>
                    </th>
                    <td className="py-3 pr-3">
                      <KindChip kind={o.kind} />
                    </td>
                    <td className="py-3 pr-3">
                      <AudienceChip offer={o} />
                    </td>
                    <td className="py-3 pr-3 whitespace-nowrap">{validityText(o)}</td>
                    <td className="py-3 pr-3 tabular-nums">{o.redemptions}</td>
                    <td className="py-3 pr-3">{activeSwitch(o)}</td>
                    <td className="py-3">{actions(o)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="tablet:block hidden">
              {items.map((o) => (
                <li
                  key={o.id}
                  className="border-line border-b py-3.5 first:pt-0 last:border-b-0 last:pb-0"
                >
                  <div className="mb-1.5 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-bold">{o.title}</p>
                      <p className="text-muted-foreground text-[11px]">{valueText(o)}</p>
                    </div>
                    {activeSwitch(o)}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <KindChip kind={o.kind} />
                    <AudienceChip offer={o} />
                  </div>
                  <p className="text-muted-foreground mt-1.5 text-[11px]">
                    {validityText(o)} · {o.redemptions} redeemed
                  </p>
                  <div className="mt-2">{actions(o)}</div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>

      {editing !== undefined && packages.data && (
        <OfferDialog
          key={editing?.id ?? 'new'}
          offer={editing}
          packages={packages.data}
          onClose={() => setEditing(undefined)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this offer?"
        description={
          deleting
            ? `“${deleting.title}” will disappear from subscribers’ Offers pages. An offer with redemptions cannot be deleted; deactivate it instead.`
            : ''
        }
        confirmLabel="Delete offer"
        onConfirm={remove}
        busy={deleteBusy}
      />
    </>
  );
}
