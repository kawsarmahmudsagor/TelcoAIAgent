'use client';

import { useMemo, useState } from 'react';
import {
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  PowerIcon,
  PowerOffIcon,
  SearchIcon,
  Trash2Icon,
} from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { PageHeader } from '@/components/dashboard/page-header';
import { StatusPill, type StatusTone } from '@/components/dashboard/status-pill';
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
import { type Offer, api } from '@/lib/api-client';
import { formatShortDay } from '@/lib/format';
import { OFFER_TYPE_LABEL, offerHeadline } from '@/lib/offers';
import { OfferDialog } from './offer-dialog';

type Phase = 'running' | 'scheduled' | 'expired' | 'off';
type Shown = Phase | 'all';

const PHASE: Record<Phase, { label: string; tone: StatusTone }> = {
  running: { label: 'Running', tone: 'success' },
  scheduled: { label: 'Scheduled', tone: 'info' },
  expired: { label: 'Expired', tone: 'warning' },
  off: { label: 'Off', tone: 'muted' },
};

/** Today as "YYYY-MM-DD" in the browser's timezone (the backend decides in the agency's). */
function localToday(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function phaseOf(offer: Offer, today: string): Phase {
  if (!offer.is_active) return 'off';
  if (offer.starts_on && offer.starts_on > today) return 'scheduled';
  if (offer.ends_on && offer.ends_on < today) return 'expired';
  return 'running';
}

function windowLabel(offer: Offer): string {
  if (!offer.starts_on && !offer.ends_on) return 'No end date';
  if (!offer.starts_on) return `Until ${formatShortDay(offer.ends_on!)}`;
  if (!offer.ends_on) return `From ${formatShortDay(offer.starts_on)}`;
  return `${formatShortDay(offer.starts_on)} – ${formatShortDay(offer.ends_on)}`;
}

function AppliesTo({ offer }: { offer: Offer }) {
  if (offer.applies_to_all_sale) return <span>All homes for sale</span>;
  const count = offer.properties.length;
  if (count === 0) return <span className="text-muted-foreground">No listings</span>;
  const stale = offer.properties.filter((p) => !p.is_active || p.listing_type !== 'sale').length;
  return (
    <span className="block min-w-0" title={offer.properties.map((p) => p.title).join('\n')}>
      <span className="block truncate">{offer.properties[0].title}</span>
      <span className="text-muted-foreground block text-xs">
        {count > 1 && `+${count - 1} more`}
        {count > 1 && stale > 0 && ' · '}
        {stale > 0 && `${stale} no longer for sale`}
      </span>
    </span>
  );
}

export function OffersView() {
  const offers = useLoad(() => api.offers.list(), [], {
    fallbackError: 'Could not load offers.',
  });
  const [shown, setShown] = useState<Shown>('all');
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<Offer | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState<Offer | null>(null);
  const [busy, setBusy] = useState(false);
  const today = localToday();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (offers.data ?? []).filter(
      (o) =>
        (shown === 'all' || phaseOf(o, today) === shown) &&
        (!q ||
          o.title.toLowerCase().includes(q) ||
          o.properties.some((p) => p.title.toLowerCase().includes(q)))
    );
  }, [offers.data, shown, query, today]);

  function replace(saved: Offer) {
    const list = offers.data ?? [];
    const exists = list.some((o) => o.id === saved.id);
    offers.setData(exists ? list.map((o) => (o.id === saved.id ? saved : o)) : [saved, ...list]);
  }

  async function setActive(o: Offer, active: boolean) {
    setBusy(true);
    try {
      replace(await api.offers.update(o.id, { is_active: active }));
      toast.success(active ? 'Offer turned on' : 'Offer turned off', { description: o.title });
    } catch (err) {
      toast.error('Could not update the offer', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove(o: Offer) {
    setBusy(true);
    try {
      await api.offers.delete(o.id);
      offers.setData((offers.data ?? []).filter((x) => x.id !== o.id));
      toast.success('Offer deleted', { description: o.title });
      setDeleting(null);
    } catch (err) {
      toast.error('Could not delete the offer', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  function openEditor(o: Offer | null) {
    setEditing(o);
    setDialogOpen(true);
  }

  return (
    <>
      <PageHeader
        title="Offers"
        description="Discounts and payment perks on homes for sale. The agent quotes only offers that are running, and the website shows them on the home page and listings."
        actions={
          <Button onClick={() => openEditor(null)}>
            <PlusIcon aria-hidden="true" />
            Add offer
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
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search offer or listing"
            aria-label="Search offers"
            className="pl-8"
            type="search"
          />
        </div>
        <Select value={shown} onValueChange={(v) => setShown(v as Shown)}>
          <SelectTrigger className="w-36" aria-label="Status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All offers</SelectItem>
            {(Object.keys(PHASE) as Phase[]).map((p) => (
              <SelectItem key={p} value={p}>
                {PHASE[p].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {offers.data && (
          <p className="text-muted-foreground ml-auto text-sm tabular-nums">
            {filtered.length} {filtered.length === 1 ? 'offer' : 'offers'}
          </p>
        )}
      </div>

      <Panel>
        {offers.loading || offers.error || filtered.length === 0 ? (
          <TableState
            loading={offers.loading}
            error={offers.error}
            onRetry={() => void offers.retry()}
            empty={
              (offers.data?.length ?? 0) === 0 ? (
                <>
                  <p className="text-foreground font-medium">No offers yet</p>
                  <p>Add a discount or a payment perk on homes for sale.</p>
                </>
              ) : (
                <>
                  <p className="text-foreground font-medium">No offers match</p>
                  <p>Try another status or clear the search.</p>
                </>
              )
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-full min-w-56">Offer</TableHead>
                <TableHead>Deal</TableHead>
                <TableHead className="min-w-44">Applies to</TableHead>
                <TableHead>Dates</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((o) => {
                const phase = PHASE[phaseOf(o, today)];
                return (
                  <TableRow key={o.id} className={o.is_active ? undefined : 'opacity-70'}>
                    <TableCell className="max-w-0 py-2">
                      <button
                        type="button"
                        onClick={() => openEditor(o)}
                        className="group focus-visible:ring-ring/50 block w-full min-w-0 rounded-sm text-left outline-none focus-visible:ring-[3px]"
                      >
                        <span className="block truncate font-medium group-hover:underline group-hover:underline-offset-2">
                          {o.title}
                        </span>
                        <span className="text-muted-foreground block truncate text-xs">
                          {OFFER_TYPE_LABEL[o.offer_type]}
                        </span>
                      </button>
                    </TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {offerHeadline(o)}
                    </TableCell>
                    <TableCell className="max-w-56">
                      <AppliesTo offer={o} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{windowLabel(o)}</TableCell>
                    <TableCell>
                      <StatusPill tone={phase.tone}>{phase.label}</StatusPill>
                    </TableCell>
                    <TableCell className="py-1.5">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`Actions for ${o.title}`}
                          >
                            <MoreHorizontalIcon aria-hidden="true" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          <DropdownMenuItem onSelect={() => openEditor(o)}>
                            <PencilIcon aria-hidden="true" />
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() => void setActive(o, !o.is_active)}
                            disabled={busy}
                          >
                            {o.is_active ? (
                              <PowerOffIcon aria-hidden="true" />
                            ) : (
                              <PowerIcon aria-hidden="true" />
                            )}
                            {o.is_active ? 'Turn off' : 'Turn on'}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(o)}>
                            <Trash2Icon aria-hidden="true" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Panel>

      <OfferDialog
        open={dialogOpen}
        offer={editing}
        onOpenChange={setDialogOpen}
        onSaved={(saved) => {
          replace(saved);
          setDialogOpen(false);
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this offer?"
        description={
          <>
            <span className="text-foreground font-medium">{deleting?.title}</span> disappears from
            the website and the agent stops quoting it. To pause it instead, turn it off.
          </>
        }
        confirmLabel="Delete offer"
        onConfirm={() => (deleting ? remove(deleting) : undefined)}
        busy={busy}
      />
    </>
  );
}
