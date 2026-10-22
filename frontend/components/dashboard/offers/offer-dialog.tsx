'use client';

import { useMemo, useState } from 'react';
import { Loader2Icon, SearchIcon } from 'lucide-react';
import { toast } from 'sonner';
import { FormField } from '@/components/dashboard/form-field';
import { SwitchRow } from '@/components/dashboard/switch-row';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useLoad } from '@/hooks/useLoad';
import { type Offer, type OfferCreate, type OfferType, api } from '@/lib/api-client';
import { formatBdt } from '@/lib/format';
import {
  AMOUNT_OPTIONAL_TYPES,
  AMOUNT_REQUIRED_TYPES,
  OFFER_TYPE_LABEL,
  PERCENT_TYPES,
} from '@/lib/offers';
import { cn } from '@/lib/shadcn/utils';

interface Form {
  title: string;
  offer_type: OfferType;
  discount_percent: string;
  discount_amount: string;
  description: string;
  terms: string;
  starts_on: string;
  ends_on: string;
  is_active: boolean;
  applies_to_all_sale: boolean;
  property_ids: string[];
}

const EMPTY: Form = {
  title: '',
  offer_type: 'percent_discount',
  discount_percent: '',
  discount_amount: '',
  description: '',
  terms: '',
  starts_on: '',
  ends_on: '',
  is_active: true,
  applies_to_all_sale: false,
  property_ids: [],
};

function formFrom(o: Offer): Form {
  return {
    title: o.title,
    offer_type: o.offer_type,
    discount_percent: o.discount_percent === null ? '' : String(o.discount_percent),
    discount_amount: o.discount_amount === null ? '' : String(o.discount_amount),
    description: o.description ?? '',
    terms: o.terms ?? '',
    starts_on: o.starts_on ?? '',
    ends_on: o.ends_on ?? '',
    is_active: o.is_active,
    applies_to_all_sale: o.applies_to_all_sale,
    property_ids: o.property_ids,
  };
}

const showsPercent = (t: OfferType) => PERCENT_TYPES.includes(t);
const showsAmount = (t: OfferType) =>
  AMOUNT_REQUIRED_TYPES.includes(t) || AMOUNT_OPTIONAL_TYPES.includes(t);

type Errors = Partial<Record<keyof Form, string>>;

function validate(form: Form): { payload: OfferCreate } | { errors: Errors } {
  const errors: Errors = {};
  if (!form.title.trim()) errors.title = 'Give the offer a title.';
  let percent: number | null = null;
  if (showsPercent(form.offer_type)) {
    percent = Number(form.discount_percent);
    if (!form.discount_percent.trim() || !Number.isFinite(percent) || percent <= 0 || percent > 100)
      errors.discount_percent = 'A percentage between 0 and 100.';
  }
  let amount: number | null = null;
  if (showsAmount(form.offer_type) && form.discount_amount.trim()) {
    amount = Number(form.discount_amount);
    if (!Number.isFinite(amount) || amount <= 0) errors.discount_amount = 'An amount in taka.';
  } else if (AMOUNT_REQUIRED_TYPES.includes(form.offer_type)) {
    errors.discount_amount = 'Enter the discount in taka.';
  }
  if (form.starts_on && form.ends_on && form.ends_on < form.starts_on)
    errors.ends_on = 'The last day can’t be before the first.';
  if (!form.applies_to_all_sale && form.property_ids.length === 0)
    errors.property_ids = 'Pick at least one home for sale, or apply it to all of them.';
  if (Object.keys(errors).length) return { errors };

  return {
    payload: {
      title: form.title.trim(),
      offer_type: form.offer_type,
      discount_percent: percent,
      discount_amount: amount,
      description: form.description.trim() || null,
      terms: form.terms.trim() || null,
      starts_on: form.starts_on || null,
      ends_on: form.ends_on || null,
      is_active: form.is_active,
      applies_to_all_sale: form.applies_to_all_sale,
      property_ids: form.applies_to_all_sale ? [] : form.property_ids,
    },
  };
}

export function OfferDialog({
  open,
  offer,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  /** null = adding a new offer. */
  offer: Offer | null;
  onOpenChange: (open: boolean) => void;
  onSaved: (offer: Offer) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-2xl">
        {open && (
          <OfferForm
            key={offer?.id ?? 'new'}
            offer={offer}
            onCancel={() => onOpenChange(false)}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function OfferForm({
  offer,
  onCancel,
  onSaved,
}: {
  offer: Offer | null;
  onCancel: () => void;
  onSaved: (offer: Offer) => void;
}) {
  const [form, setForm] = useState<Form>(() => (offer ? formFrom(offer) : EMPTY));
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function text(key: keyof Form) {
    return {
      value: form[key] as string,
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        set(key, e.target.value as never),
    };
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const result = validate(form);
    if ('errors' in result) {
      setErrors(result.errors);
      return;
    }
    setSaving(true);
    setServerError(null);
    try {
      const saved = offer
        ? await api.offers.update(offer.id, result.payload)
        : await api.offers.create(result.payload);
      toast.success(offer ? 'Offer saved' : 'Offer added', { description: saved.title });
      onSaved(saved);
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Could not save the offer.');
    } finally {
      setSaving(false);
    }
  }

  const percentShown = showsPercent(form.offer_type);
  const amountShown = showsAmount(form.offer_type);
  const amountRequired = AMOUNT_REQUIRED_TYPES.includes(form.offer_type);

  return (
    <>
      <DialogHeader>
        <DialogTitle>{offer ? 'Edit offer' : 'Add offer'}</DialogTitle>
        <DialogDescription>
          Offers apply to homes for sale only. The agent quotes running offers word for word and
          never makes up its own.
        </DialogDescription>
      </DialogHeader>

      <form id="offer-form" onSubmit={submit} noValidate className="grid gap-6">
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="sr-only">The offer</legend>
          <FormField id="o-title" label="Title" error={errors.title} className="sm:col-span-2">
            {(c) => (
              <Input
                {...c}
                {...text('title')}
                maxLength={255}
                autoFocus={!offer}
                placeholder="Tk 10 lakh off on booking"
              />
            )}
          </FormField>
          <FormField id="o-type" label="Type" className="sm:col-span-2">
            {(c) => (
              <Select
                value={form.offer_type}
                onValueChange={(v) => set('offer_type', v as OfferType)}
              >
                <SelectTrigger {...c} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(OFFER_TYPE_LABEL) as OfferType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {OFFER_TYPE_LABEL[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
          {percentShown && (
            <FormField id="o-percent" label="Discount (%)" error={errors.discount_percent}>
              {(c) => (
                <Input
                  {...c}
                  {...text('discount_percent')}
                  type="number"
                  min={0}
                  max={100}
                  step={0.5}
                  inputMode="decimal"
                />
              )}
            </FormField>
          )}
          {amountShown && (
            <FormField
              id="o-amount"
              label={
                form.offer_type === 'reduced_booking_money'
                  ? 'Booking money (৳)'
                  : form.offer_type === 'fee_waiver'
                    ? 'Fees waived (৳)'
                    : 'Discount (৳)'
              }
              error={errors.discount_amount}
              hint={
                amountRequired
                  ? form.discount_amount && Number(form.discount_amount) > 0
                    ? formatBdt(Number(form.discount_amount))
                    : undefined
                  : 'Optional.'
              }
            >
              {(c) => (
                <Input
                  {...c}
                  {...text('discount_amount')}
                  type="number"
                  min={0}
                  inputMode="numeric"
                />
              )}
            </FormField>
          )}
          <FormField
            id="o-description"
            label="Description"
            hint="Shown on the website and read by the agent."
            className="sm:col-span-2"
          >
            {(c) => <Textarea {...c} {...text('description')} className="max-h-40 min-h-20" />}
          </FormField>
          <FormField
            id="o-terms"
            label="Terms"
            hint="Conditions the agent must mention, e.g. payment deadlines."
            className="sm:col-span-2"
          >
            {(c) => <Textarea {...c} {...text('terms')} className="max-h-40 min-h-16" />}
          </FormField>
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="mb-3 text-sm font-semibold">Dates</legend>
          <FormField id="o-starts" label="First day" hint="Optional. Dhaka time.">
            {(c) => <Input {...c} {...text('starts_on')} type="date" />}
          </FormField>
          <FormField id="o-ends" label="Last day" error={errors.ends_on} hint="Optional.">
            {(c) => <Input {...c} {...text('ends_on')} type="date" min={form.starts_on} />}
          </FormField>
        </fieldset>

        <fieldset className="grid gap-3">
          <legend className="mb-3 text-sm font-semibold">Homes</legend>
          <div className="divide-y rounded-md border px-3">
            <SwitchRow
              label="All homes for sale"
              description="Applies to every active sale listing, including ones added later."
              checked={form.applies_to_all_sale}
              onCheckedChange={(v) => set('applies_to_all_sale', v)}
            />
          </div>
          {!form.applies_to_all_sale && (
            <SalePropertyPicker
              selected={form.property_ids}
              linked={offer?.properties ?? []}
              onChange={(ids) => set('property_ids', ids)}
              error={errors.property_ids}
            />
          )}
        </fieldset>

        <fieldset className="divide-y rounded-md border px-3">
          <legend className="sr-only">Visibility</legend>
          <SwitchRow
            label="Active"
            description="Turned-off offers are hidden from the agent and the website."
            checked={form.is_active}
            onCheckedChange={(v) => set('is_active', v)}
          />
        </fieldset>

        {serverError && (
          <p
            className="bg-destructive/8 text-destructive rounded-md px-3 py-2 text-sm"
            role="alert"
          >
            {serverError}
          </p>
        )}
      </form>

      <DialogFooter>
        <Button variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" form="offer-form" disabled={saving}>
          {saving && <Loader2Icon className="animate-spin" aria-hidden="true" />}
          {offer ? 'Save offer' : 'Add offer'}
        </Button>
      </DialogFooter>
    </>
  );
}

interface PickerItem {
  id: string;
  title: string;
  area: string;
  price: number | null;
  /** Linked earlier but no longer an active sale listing: can only be removed. */
  stale: boolean;
}

/** Multi-select of active sale listings, with a search. Listings linked earlier that have since
 * gone inactive or to rent are listed too (flagged), so they can be unticked. */
function SalePropertyPicker({
  selected,
  linked,
  onChange,
  error,
}: {
  selected: string[];
  linked: Offer['properties'];
  onChange: (ids: string[]) => void;
  error?: string;
}) {
  const properties = useLoad(() => api.properties.list({ limit: 1000 }), [], {
    fallbackError: 'Could not load listings.',
  });
  const [query, setQuery] = useState('');

  const items = useMemo<PickerItem[]>(() => {
    const sale = (properties.data ?? [])
      .filter((p) => p.is_active && p.listing_type === 'sale')
      .map((p) => ({
        id: p.id,
        title: p.title,
        area: [p.neighborhood, p.city].filter(Boolean).join(', '),
        price: p.price,
        stale: false,
      }));
    const saleIds = new Set(sale.map((p) => p.id));
    const stale = linked
      .filter((p) => !saleIds.has(p.id) && selected.includes(p.id))
      .map((p) => ({
        id: p.id,
        title: p.title,
        area: [p.neighborhood, p.city].filter(Boolean).join(', '),
        price: null,
        stale: true,
      }));
    return [...stale, ...sale];
  }, [properties.data, linked, selected]);

  const q = query.trim().toLowerCase();
  const visible = q
    ? items.filter((p) => p.title.toLowerCase().includes(q) || p.area.toLowerCase().includes(q))
    : items;
  const chosen = new Set(selected);

  function toggle(id: string, on: boolean) {
    onChange(on ? [...selected, id] : selected.filter((x) => x !== id));
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="relative w-full sm:w-64">
          <SearchIcon
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search homes for sale"
            aria-label="Search homes for sale"
            className="pl-8"
            type="search"
          />
        </div>
        <p className="text-muted-foreground text-sm tabular-nums" aria-live="polite">
          {selected.length} selected
        </p>
      </div>
      <div
        role="group"
        aria-label="Homes for sale"
        aria-describedby={error ? 'o-props-error' : undefined}
        className={cn('max-h-64 overflow-y-auto rounded-md border', error && 'border-destructive')}
      >
        {properties.loading ? (
          <p className="text-muted-foreground p-3 text-sm">Loading listings…</p>
        ) : properties.error ? (
          <p className="text-destructive p-3 text-sm" role="alert">
            {properties.error}
          </p>
        ) : visible.length === 0 ? (
          <p className="text-muted-foreground p-3 text-sm">No homes for sale match.</p>
        ) : (
          <ul className="divide-y">
            {visible.map((p) => {
              const id = `o-prop-${p.id}`;
              return (
                <li key={p.id} className="flex items-center gap-3 px-3 py-2">
                  <Checkbox
                    id={id}
                    checked={chosen.has(p.id)}
                    onCheckedChange={(v) => toggle(p.id, v === true)}
                  />
                  <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer text-sm">
                    <span className="block truncate font-medium">{p.title}</span>
                    <span className="text-muted-foreground block truncate text-xs">
                      {p.stale ? 'No longer an active sale listing' : p.area}
                    </span>
                  </label>
                  {p.price !== null && (
                    <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                      {formatBdt(p.price)}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {error && (
        <p id="o-props-error" className="text-destructive text-xs" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
