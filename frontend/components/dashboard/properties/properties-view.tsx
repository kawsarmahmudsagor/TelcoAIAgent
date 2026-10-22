'use client';

import { useMemo, useState } from 'react';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  EyeOffIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  RotateCcwIcon,
  SearchIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { PageHeader } from '@/components/dashboard/page-header';
import { StatusPill } from '@/components/dashboard/status-pill';
import { LISTING_TYPE, PROPERTY_TYPE } from '@/components/dashboard/status-tones';
import { Panel, TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useLoad } from '@/hooks/useLoad';
import { type ListingType, type Property, type PropertyType, api } from '@/lib/api-client';
import { formatBdt } from '@/lib/format';
import { ListingPhoto } from './listing-photo';
import { PropertyDialog } from './property-dialog';

const PAGE_SIZE = 25;
type Shown = 'active' | 'inactive' | 'all';

export function PropertiesView() {
  const listings = useLoad(() => api.properties.list({ limit: 1000 }), [], {
    fallbackError: 'Could not load listings.',
  });
  const [type, setType] = useState<PropertyType | 'all'>('all');
  const [listing, setListing] = useState<ListingType | 'all'>('all');
  const [shown, setShown] = useState<Shown>('active');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<Property | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deactivating, setDeactivating] = useState<Property | null>(null);
  const [busy, setBusy] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (listings.data ?? []).filter(
      (p) =>
        (type === 'all' || p.property_type === type) &&
        (listing === 'all' || p.listing_type === listing) &&
        (shown === 'all' || p.is_active === (shown === 'active')) &&
        (!q ||
          p.title.toLowerCase().includes(q) ||
          (p.neighborhood ?? '').toLowerCase().includes(q) ||
          p.address_line.toLowerCase().includes(q))
    );
  }, [listings.data, type, listing, shown, query]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const rows = filtered.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  function filter<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(0);
    };
  }

  function replace(saved: Property) {
    const list = listings.data ?? [];
    const exists = list.some((p) => p.id === saved.id);
    listings.setData(exists ? list.map((p) => (p.id === saved.id ? saved : p)) : [saved, ...list]);
  }

  async function setActive(p: Property, active: boolean) {
    setBusy(true);
    try {
      if (active) {
        replace(await api.properties.update(p.id, { is_active: true }));
        toast.success('Listing reactivated', { description: p.title });
      } else {
        await api.properties.delete(p.id);
        replace({ ...p, is_active: false });
        toast.success('Listing deactivated', { description: p.title });
      }
      setDeactivating(null);
    } catch (err) {
      toast.error(active ? 'Could not reactivate' : 'Could not deactivate', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  function openEditor(p: Property | null) {
    setEditing(p);
    setDialogOpen(true);
  }

  return (
    <>
      <PageHeader
        title="Properties"
        description="The flats, houses and plots the agent can offer, with their photos."
        actions={
          <Button onClick={() => openEditor(null)}>
            <PlusIcon aria-hidden="true" />
            Add listing
          </Button>
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <SearchIcon
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(e) => filter(setQuery)(e.target.value)}
            placeholder="Search title or area"
            aria-label="Search listings"
            className="pl-8"
            type="search"
          />
        </div>
        <Select value={type} onValueChange={(v) => filter(setType)(v as typeof type)}>
          <SelectTrigger className="w-36" aria-label="Type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {(Object.keys(PROPERTY_TYPE) as PropertyType[]).map((t) => (
              <SelectItem key={t} value={t}>
                {PROPERTY_TYPE[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={listing} onValueChange={(v) => filter(setListing)(v as typeof listing)}>
          <SelectTrigger className="w-36" aria-label="Rent or sale">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Rent and sale</SelectItem>
            <SelectItem value="rent">For rent</SelectItem>
            <SelectItem value="sale">For sale</SelectItem>
          </SelectContent>
        </Select>
        <Select value={shown} onValueChange={(v) => filter(setShown)(v as Shown)}>
          <SelectTrigger className="w-32" aria-label="Active or not">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
        {listings.data && (
          <p className="text-muted-foreground ml-auto text-sm tabular-nums">
            {filtered.length} {filtered.length === 1 ? 'listing' : 'listings'}
          </p>
        )}
      </div>

      <Panel>
        {listings.loading || listings.error || rows.length === 0 ? (
          <TableState
            loading={listings.loading}
            error={listings.error}
            onRetry={() => void listings.retry()}
            empty={
              (listings.data?.length ?? 0) === 0 ? (
                <>
                  <p className="text-foreground font-medium">No listings yet</p>
                  <p>Add a flat with its price and photos and the agent can offer it.</p>
                </>
              ) : (
                <>
                  <p className="text-foreground font-medium">No listings match</p>
                  <p>Try another type or clear the search.</p>
                </>
              )
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-full min-w-64">Listing</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Beds</TableHead>
                <TableHead className="text-right">Baths</TableHead>
                <TableHead className="text-right">Sq ft</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id} className={p.is_active ? undefined : 'opacity-70'}>
                  <TableCell className="max-w-0 py-2">
                    <button
                      type="button"
                      onClick={() => openEditor(p)}
                      className="group focus-visible:ring-ring/50 flex w-full min-w-0 items-center gap-3 rounded-sm text-left outline-none focus-visible:ring-[3px]"
                    >
                      <ListingPhoto
                        src={p.image_url ?? p.images?.[0]}
                        alt=""
                        className="h-11 w-16 shrink-0 rounded-md"
                      />
                      <span className="min-w-0">
                        <span className="block truncate font-medium group-hover:underline group-hover:underline-offset-2">
                          {p.title}
                        </span>
                        <span className="text-muted-foreground block truncate text-xs">
                          {[p.neighborhood, p.city].filter(Boolean).join(', ')}
                        </span>
                      </span>
                    </button>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {PROPERTY_TYPE[p.property_type] ?? p.property_type}
                    <span className="text-muted-foreground block text-xs">
                      {LISTING_TYPE[p.listing_type] ?? p.listing_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap tabular-nums">
                    {formatBdt(p.price)}
                    {p.listing_type === 'rent' && (
                      <span className="text-muted-foreground text-xs">/mo</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{p.bedrooms}</TableCell>
                  <TableCell className="text-right tabular-nums">{p.bathrooms}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {p.sqft?.toLocaleString() ?? '—'}
                  </TableCell>
                  <TableCell>
                    {/* Active is the norm; only the exceptions get a pill, so rows stay one line. */}
                    <span className="flex flex-wrap gap-1">
                      {!p.is_active && <StatusPill tone="muted">Inactive</StatusPill>}
                      {p.is_featured && <StatusPill tone="brass">Featured</StatusPill>}
                      {p.is_active && !p.is_featured && (
                        <span className="text-muted-foreground text-sm">Active</span>
                      )}
                    </span>
                  </TableCell>
                  <TableCell className="py-1.5">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Actions for ${p.title}`}
                        >
                          <MoreHorizontalIcon aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-44">
                        <DropdownMenuItem onSelect={() => openEditor(p)}>
                          <PencilIcon aria-hidden="true" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        {p.is_active ? (
                          <DropdownMenuItem
                            variant="destructive"
                            onSelect={() => setDeactivating(p)}
                          >
                            <EyeOffIcon aria-hidden="true" />
                            Deactivate
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem
                            onSelect={() => void setActive(p, true)}
                            disabled={busy}
                          >
                            <RotateCcwIcon aria-hidden="true" />
                            Reactivate
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>

      {pageCount > 1 && (
        <nav
          aria-label="Pages"
          className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"
        >
          <p className="text-muted-foreground tabular-nums">
            Page {current + 1} of {pageCount}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(current - 1)}
              disabled={current === 0}
            >
              <ChevronLeftIcon aria-hidden="true" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(current + 1)}
              disabled={current + 1 >= pageCount}
            >
              Next
              <ChevronRightIcon aria-hidden="true" />
            </Button>
          </div>
        </nav>
      )}

      <PropertyDialog
        open={dialogOpen}
        property={editing}
        onOpenChange={setDialogOpen}
        onSaved={(saved) => {
          replace(saved);
          setDialogOpen(false);
        }}
      />
      <ConfirmDialog
        open={deactivating !== null}
        onOpenChange={(open) => !open && setDeactivating(null)}
        title="Deactivate this listing?"
        description={
          <>
            <span className="text-foreground font-medium">{deactivating?.title}</span> is hidden
            from the agent and the website. Past bookings keep it, and you can reactivate it later.
          </>
        }
        confirmLabel="Deactivate listing"
        onConfirm={() => (deactivating ? setActive(deactivating, false) : undefined)}
        busy={busy}
      />
    </>
  );
}
