'use client';

import { useState } from 'react';
import { Loader2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { FormField } from '@/components/dashboard/form-field';
import { LISTING_TYPE, PROPERTY_TYPE } from '@/components/dashboard/status-tones';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  type ListingType,
  type Property,
  type PropertyCreate,
  type PropertyType,
  api,
} from '@/lib/api-client';
import { ListingPhoto } from './listing-photo';

interface Form {
  title: string;
  property_type: PropertyType;
  listing_type: ListingType;
  price: string;
  bedrooms: string;
  bathrooms: string;
  sqft: string;
  address_line: string;
  neighborhood: string;
  city: string;
  available_from: string;
  amenities: string;
  description: string;
  cover: string;
  gallery: string;
  is_active: boolean;
  is_featured: boolean;
}

const EMPTY: Form = {
  title: '',
  property_type: 'apartment',
  listing_type: 'rent',
  price: '',
  bedrooms: '2',
  bathrooms: '2',
  sqft: '',
  address_line: '',
  neighborhood: '',
  city: 'Dhaka',
  available_from: '',
  amenities: '',
  description: '',
  cover: '',
  gallery: '',
  is_active: true,
  is_featured: false,
};

function formFrom(p: Property): Form {
  // `images` is the whole gallery with the cover first; the cover is also `image_url`.
  const cover = p.image_url ?? p.images?.[0] ?? '';
  const gallery = (p.images ?? []).filter((url) => url !== cover);
  return {
    title: p.title,
    property_type: p.property_type,
    listing_type: p.listing_type,
    price: String(p.price),
    bedrooms: String(p.bedrooms),
    bathrooms: String(p.bathrooms),
    sqft: p.sqft === null ? '' : String(p.sqft),
    address_line: p.address_line,
    neighborhood: p.neighborhood ?? '',
    city: p.city,
    available_from: p.available_from ?? '',
    amenities: p.amenities.join(', '),
    description: p.description ?? '',
    cover,
    gallery: gallery.join('\n'),
    is_active: p.is_active,
    is_featured: p.is_featured,
  };
}

function urlsIn(text: string): string[] {
  return Array.from(
    new Set(
      text
        .split(/[\n,]+/)
        .map((u) => u.trim())
        .filter(Boolean)
    )
  );
}

const isUrl = (value: string) => /^https?:\/\/\S+$/i.test(value) || value.startsWith('/');

type Errors = Partial<Record<keyof Form, string>>;

function validate(form: Form): { payload: PropertyCreate } | { errors: Errors } {
  const errors: Errors = {};
  if (!form.title.trim()) errors.title = 'Give the listing a title.';
  if (!form.address_line.trim()) errors.address_line = 'Enter the street address.';
  if (!form.city.trim()) errors.city = 'Enter the city.';
  const price = Number(form.price);
  if (!form.price.trim() || !Number.isFinite(price) || price < 0)
    errors.price = 'Enter the price in taka.';
  const bedrooms = Number(form.bedrooms);
  if (!Number.isInteger(bedrooms) || bedrooms < 0) errors.bedrooms = 'A whole number, 0 or more.';
  const bathrooms = Number(form.bathrooms);
  if (!Number.isFinite(bathrooms) || bathrooms < 0) errors.bathrooms = '0 or more.';
  const sqft = form.sqft.trim() ? Number(form.sqft) : null;
  if (sqft !== null && (!Number.isInteger(sqft) || sqft <= 0))
    errors.sqft = 'A whole number of square feet.';
  const cover = form.cover.trim();
  if (cover && !isUrl(cover)) errors.cover = 'Use a full https:// address.';
  const gallery = urlsIn(form.gallery);
  if (gallery.some((u) => !isUrl(u)))
    errors.gallery = 'Every line must be a full https:// address.';
  if (Object.keys(errors).length) return { errors };

  const images = cover ? [cover, ...gallery.filter((u) => u !== cover)] : gallery;
  return {
    payload: {
      title: form.title.trim(),
      property_type: form.property_type,
      listing_type: form.listing_type,
      price,
      bedrooms,
      bathrooms,
      sqft,
      address_line: form.address_line.trim(),
      neighborhood: form.neighborhood.trim() || null,
      city: form.city.trim(),
      available_from: form.available_from || null,
      amenities: form.amenities
        .split(',')
        .map((a) => a.trim())
        .filter(Boolean),
      description: form.description.trim() || null,
      image_url: cover || images[0] || null,
      images: images.length ? images : null,
      is_active: form.is_active,
      is_featured: form.is_featured,
    },
  };
}

export function PropertyDialog({
  open,
  property,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  /** null = adding a new listing. */
  property: Property | null;
  onOpenChange: (open: boolean) => void;
  onSaved: (property: Property) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-2xl">
        {open && (
          <PropertyForm
            key={property?.id ?? 'new'}
            property={property}
            onCancel={() => onOpenChange(false)}
            onSaved={onSaved}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function PropertyForm({
  property,
  onCancel,
  onSaved,
}: {
  property: Property | null;
  onCancel: () => void;
  onSaved: (property: Property) => void;
}) {
  const [form, setForm] = useState<Form>(() => (property ? formFrom(property) : EMPTY));
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
      const saved = property
        ? await api.properties.update(property.id, result.payload)
        : await api.properties.create(result.payload);
      toast.success(property ? 'Listing saved' : 'Listing added', { description: saved.title });
      onSaved(saved);
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Could not save the listing.');
    } finally {
      setSaving(false);
    }
  }

  const gallery = urlsIn(form.gallery).filter(isUrl);
  const cover = form.cover.trim();

  return (
    <>
      <DialogHeader>
        <DialogTitle>{property ? 'Edit listing' : 'Add listing'}</DialogTitle>
        <DialogDescription>
          The agent can offer active listings in chats and calls straight away.
        </DialogDescription>
      </DialogHeader>

      <form id="property-form" onSubmit={submit} noValidate className="grid gap-6">
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="sr-only">Basics</legend>
          <FormField id="p-title" label="Title" error={errors.title} className="sm:col-span-2">
            {(c) => <Input {...c} {...text('title')} maxLength={255} autoFocus={!property} />}
          </FormField>
          <FormField id="p-type" label="Type">
            {(c) => (
              <Select
                value={form.property_type}
                onValueChange={(v) => set('property_type', v as PropertyType)}
              >
                <SelectTrigger {...c} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(PROPERTY_TYPE) as PropertyType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {PROPERTY_TYPE[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
          <FormField id="p-listing" label="For">
            {(c) => (
              <Select
                value={form.listing_type}
                onValueChange={(v) => set('listing_type', v as ListingType)}
              >
                <SelectTrigger {...c} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(LISTING_TYPE) as ListingType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {LISTING_TYPE[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
          <FormField
            id="p-price"
            label={form.listing_type === 'rent' ? 'Rent per month (৳)' : 'Price (৳)'}
            error={errors.price}
          >
            {(c) => <Input {...c} {...text('price')} type="number" min={0} inputMode="numeric" />}
          </FormField>
          <FormField id="p-sqft" label="Size (sq ft)" error={errors.sqft} hint="Optional.">
            {(c) => <Input {...c} {...text('sqft')} type="number" min={1} inputMode="numeric" />}
          </FormField>
          <FormField id="p-bedrooms" label="Bedrooms" error={errors.bedrooms}>
            {(c) => (
              <Input {...c} {...text('bedrooms')} type="number" min={0} inputMode="numeric" />
            )}
          </FormField>
          <FormField id="p-bathrooms" label="Bathrooms" error={errors.bathrooms}>
            {(c) => (
              <Input
                {...c}
                {...text('bathrooms')}
                type="number"
                min={0}
                step={0.5}
                inputMode="decimal"
              />
            )}
          </FormField>
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="mb-3 text-sm font-semibold">Location</legend>
          <FormField
            id="p-address"
            label="Street address"
            error={errors.address_line}
            hint="Not shown on the public site."
            className="sm:col-span-2"
          >
            {(c) => <Input {...c} {...text('address_line')} autoComplete="street-address" />}
          </FormField>
          <FormField id="p-area" label="Area" hint="Gulshan, Banani, Dhanmondi…">
            {(c) => <Input {...c} {...text('neighborhood')} />}
          </FormField>
          <FormField id="p-city" label="City" error={errors.city}>
            {(c) => <Input {...c} {...text('city')} autoComplete="address-level2" />}
          </FormField>
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="mb-3 text-sm font-semibold">Details</legend>
          <FormField id="p-available" label="Available from" hint="Optional.">
            {(c) => <Input {...c} {...text('available_from')} type="date" />}
          </FormField>
          <FormField id="p-amenities" label="Amenities" hint="Comma separated.">
            {(c) => <Input {...c} {...text('amenities')} placeholder="Lift, generator, parking" />}
          </FormField>
          <FormField id="p-description" label="Description" className="sm:col-span-2">
            {(c) => <Textarea {...c} {...text('description')} className="max-h-60 min-h-24" />}
          </FormField>
        </fieldset>

        <fieldset className="grid gap-4">
          <legend className="mb-3 text-sm font-semibold">Photos</legend>
          <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
            <FormField
              id="p-cover"
              label="Cover photo URL"
              error={errors.cover}
              hint="Shown first, in chat cards and on the website."
            >
              {(c) => (
                <Input
                  {...c}
                  {...text('cover')}
                  type="url"
                  inputMode="url"
                  placeholder="https://…"
                />
              )}
            </FormField>
            <ListingPhoto
              key={cover}
              src={isUrl(cover) ? cover : null}
              alt="Cover preview"
              className="aspect-[4/3] w-full rounded-md border sm:mt-7"
            />
          </div>
          <FormField
            id="p-gallery"
            label="More photos"
            error={errors.gallery}
            hint="One URL per line, in the order they should appear after the cover."
          >
            {(c) => (
              <Textarea
                {...c}
                {...text('gallery')}
                className="max-h-40 min-h-20 font-mono text-xs"
                spellCheck={false}
                placeholder={'https://…\nhttps://…'}
              />
            )}
          </FormField>
          {gallery.length > 0 && (
            <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5" aria-label="Gallery preview">
              {gallery.map((url, i) => (
                <li key={url}>
                  <ListingPhoto
                    src={url}
                    alt={`Photo ${i + 2}`}
                    className="aspect-[4/3] w-full rounded-md border"
                  />
                </li>
              ))}
            </ul>
          )}
        </fieldset>

        <fieldset className="divide-y rounded-md border px-3">
          <legend className="sr-only">Visibility</legend>
          <SwitchRow
            label="Active"
            description="Inactive listings are hidden from the agent and the website."
            checked={form.is_active}
            onCheckedChange={(v) => set('is_active', v)}
          />
          <SwitchRow
            label="Featured"
            description="Shown first on the website's home page."
            checked={form.is_featured}
            onCheckedChange={(v) => set('is_featured', v)}
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
        <Button type="submit" form="property-form" disabled={saving}>
          {saving && <Loader2Icon className="animate-spin" aria-hidden="true" />}
          {property ? 'Save listing' : 'Add listing'}
        </Button>
      </DialogFooter>
    </>
  );
}
