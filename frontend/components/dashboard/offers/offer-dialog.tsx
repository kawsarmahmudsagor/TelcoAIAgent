'use client';

import { useState } from 'react';
import { Loader2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { FormField, SELECT } from '@/components/dashboard/form-field';
import { SegmentedFilter } from '@/components/dashboard/list-controls';
import { AUDIENCE_LABEL, KINDS, KIND_LABEL } from '@/components/dashboard/offers/offer-parts';
import { SubscriberPicker } from '@/components/dashboard/offers/subscriber-picker';
import { SwitchRow } from '@/components/dashboard/switch-row';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { adminApi } from '@/lib/admin-api';
import { invalidateAdmin } from '@/lib/admin-query';
import type {
  AdminOffer,
  AdminPackage,
  OfferAudience,
  OfferCreate,
  OfferKind,
  OfferSubscriberRef,
} from '@/lib/types/admin';

const AUDIENCES = Object.keys(AUDIENCE_LABEL) as OfferAudience[];

function num(text: string): number | null {
  const t = text.trim();
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : NaN;
}

/** Creates an offer, or edits `offer`. Mount it only while open (with a `key` per offer) so every
 * opening starts from the offer's own values. */
export function OfferDialog({
  offer,
  packages,
  onClose,
}: {
  offer: AdminOffer | null;
  packages: AdminPackage[];
  onClose: () => void;
}) {
  const [kind, setKind] = useState<OfferKind>(offer?.kind ?? 'pack');
  const [title, setTitle] = useState(offer?.title ?? '');
  const [description, setDescription] = useState(offer?.description ?? '');
  const [terms, setTerms] = useState(offer?.terms ?? '');
  const [packageId, setPackageId] = useState(offer?.package_id ?? '');
  const [pointsCost, setPointsCost] = useState(offer?.points_cost?.toString() ?? '');
  const [percent, setPercent] = useState(offer?.cashback_percent?.toString() ?? '');
  const [minRecharge, setMinRecharge] = useState(offer?.min_recharge?.toString() ?? '');
  const [cap, setCap] = useState(offer?.cashback_cap?.toString() ?? '');
  const [audience, setAudience] = useState<OfferAudience>(offer?.audience ?? 'all');
  const [picked, setPicked] = useState<OfferSubscriberRef[]>(offer?.subscribers ?? []);
  const [startsOn, setStartsOn] = useState(offer?.starts_on ?? '');
  const [endsOn, setEndsOn] = useState(offer?.ends_on ?? '');
  const [active, setActive] = useState(offer?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsPackage = kind === 'pack' || kind === 'points';
  // An offer on a package that has since left the catalogue still shows its package.
  const packageMissing = packageId !== '' && !packages.some((p) => p.id === packageId);

  const cost = num(pointsCost);
  const pct = num(percent);
  const min = num(minRecharge);
  const capValue = num(cap);
  const problem = !title.trim()
    ? 'Give the offer a title.'
    : needsPackage && !packageId
      ? 'Choose a package.'
      : kind === 'points' &&
          (cost === null || Number.isNaN(cost) || cost <= 0 || !Number.isInteger(cost))
        ? 'Points cost must be a whole number above 0.'
        : kind === 'cashback' && (pct === null || Number.isNaN(pct) || pct <= 0 || pct > 100)
          ? 'Cashback must be above 0% and at most 100%.'
          : kind === 'cashback' && (min === null || Number.isNaN(min) || min < 0)
            ? 'Set the minimum recharge.'
            : kind === 'cashback' && capValue !== null && (Number.isNaN(capValue) || capValue < 0)
              ? 'The cashback cap must be a number.'
              : audience === 'specific' && picked.length === 0
                ? 'Add at least one subscriber.'
                : startsOn && endsOn && endsOn < startsOn
                  ? 'The end date must not be before the start date.'
                  : null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (problem) return;
    // Every kind field is sent, with the other kinds' fields null, so editing can change kind.
    const body: OfferCreate = {
      title: title.trim(),
      description: description.trim() || null,
      terms: terms.trim() || null,
      package_id: needsPackage ? packageId : null,
      points_cost: kind === 'points' ? cost : null,
      cashback_percent: kind === 'cashback' ? pct : null,
      min_recharge: kind === 'cashback' ? min : null,
      cashback_cap: kind === 'cashback' ? capValue : null,
      audience,
      subscriber_ids: audience === 'specific' ? picked.map((p) => p.id) : [],
      starts_on: startsOn || null,
      ends_on: endsOn || null,
      is_active: active,
    };
    setBusy(true);
    setError(null);
    try {
      if (offer) await adminApi.updateOffer(offer.id, body);
      else await adminApi.createOffer(body);
      toast.success(offer ? 'Offer saved' : 'Offer created', { description: body.title });
      invalidateAdmin(['offers']);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the offer.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{offer ? 'Edit offer' : 'New offer'}</DialogTitle>
          <DialogDescription>
            {offer && offer.redemptions > 0
              ? `Redeemed ${offer.redemptions} ${offer.redemptions === 1 ? 'time' : 'times'}. Changes apply to new redemptions.`
              : 'Subscribers in the audience see it on their Offers page while it is active.'}
          </DialogDescription>
        </DialogHeader>
        <form id="offer-form" onSubmit={submit} className="grid gap-4">
          <div className="grid content-start gap-2">
            <span className="text-sm leading-none font-medium">Kind</span>
            <SegmentedFilter<OfferKind>
              label="Offer kind"
              value={kind}
              onChange={(k) => {
                setKind(k);
                setError(null);
              }}
              options={KINDS.map((k) => ({ value: k, label: KIND_LABEL[k] }))}
            />
            <p className="text-muted-foreground text-xs">
              {kind === 'pack'
                ? 'A package subscribers can buy through this offer.'
                : kind === 'points'
                  ? 'A package subscribers redeem with reward points.'
                  : 'A percentage back on recharges.'}
            </p>
          </div>

          <FormField id="offer-title" label="Title">
            {(control) => (
              <Input
                {...control}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={160}
                required
              />
            )}
          </FormField>

          {needsPackage && (
            <FormField id="offer-package" label="Package">
              {(control) => (
                <select
                  {...control}
                  className={SELECT}
                  value={packageId}
                  onChange={(e) => setPackageId(e.target.value)}
                  required
                >
                  <option value="" disabled>
                    Choose a package
                  </option>
                  {packageMissing && offer && (
                    <option value={packageId}>{offer.package_name ?? 'Current package'}</option>
                  )}
                  {packages.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} (৳ {p.price})
                    </option>
                  ))}
                </select>
              )}
            </FormField>
          )}
          {kind === 'points' && (
            <FormField id="offer-points" label="Points cost">
              {(control) => (
                <Input
                  {...control}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  step={1}
                  value={pointsCost}
                  onChange={(e) => setPointsCost(e.target.value)}
                />
              )}
            </FormField>
          )}
          {kind === 'cashback' && (
            <div className="phone:grid-cols-1 grid grid-cols-3 gap-4">
              <FormField id="offer-percent" label="Cashback %">
                {(control) => (
                  <Input
                    {...control}
                    type="number"
                    inputMode="decimal"
                    min={0}
                    max={100}
                    step="any"
                    value={percent}
                    onChange={(e) => setPercent(e.target.value)}
                  />
                )}
              </FormField>
              <FormField id="offer-min" label="Minimum recharge (৳)">
                {(control) => (
                  <Input
                    {...control}
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    value={minRecharge}
                    onChange={(e) => setMinRecharge(e.target.value)}
                  />
                )}
              </FormField>
              <FormField id="offer-cap" label="Cap (৳)" hint="Optional">
                {(control) => (
                  <Input
                    {...control}
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    value={cap}
                    onChange={(e) => setCap(e.target.value)}
                  />
                )}
              </FormField>
            </div>
          )}

          <FormField id="offer-description" label="Description" hint="Optional">
            {(control) => (
              <Textarea
                {...control}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            )}
          </FormField>
          <FormField id="offer-terms" label="Terms" hint="Optional">
            {(control) => (
              <Textarea {...control} value={terms} onChange={(e) => setTerms(e.target.value)} />
            )}
          </FormField>

          <FormField id="offer-audience" label="Audience">
            {(control) => (
              <select
                {...control}
                className={SELECT}
                value={audience}
                onChange={(e) => setAudience(e.target.value as OfferAudience)}
              >
                {AUDIENCES.map((a) => (
                  <option key={a} value={a}>
                    {AUDIENCE_LABEL[a]}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          {audience === 'specific' && <SubscriberPicker picked={picked} onChange={setPicked} />}

          <div className="phone:grid-cols-1 grid grid-cols-2 gap-4">
            <FormField id="offer-starts" label="Starts on" hint="Optional">
              {(control) => (
                <Input
                  {...control}
                  type="date"
                  value={startsOn}
                  onChange={(e) => setStartsOn(e.target.value)}
                />
              )}
            </FormField>
            <FormField id="offer-ends" label="Ends on" hint="Optional">
              {(control) => (
                <Input
                  {...control}
                  type="date"
                  value={endsOn}
                  onChange={(e) => setEndsOn(e.target.value)}
                />
              )}
            </FormField>
          </div>

          <SwitchRow
            label="Active"
            description="Inactive offers are hidden from subscribers."
            checked={active}
            onCheckedChange={setActive}
            className="border-t pb-0"
          />

          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : (
            problem && <p className="text-muted-foreground text-xs">{problem}</p>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="offer-form" disabled={busy || problem !== null}>
            {busy && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            {offer ? 'Save offer' : 'Create offer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
