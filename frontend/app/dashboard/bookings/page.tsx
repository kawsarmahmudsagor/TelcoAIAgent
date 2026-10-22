'use client';

import { useEffect, useState } from 'react';
import { Loader2Icon, PlusIcon } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/dashboard/page-header';
import { StatusPill } from '@/components/dashboard/status-pill';
import { BOOKING_CHANNEL, BOOKING_STATUS } from '@/components/dashboard/status-tones';
import { Panel, TableState } from '@/components/dashboard/table-state';
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
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
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
import { type Booking, type Client, type Property, api } from '@/lib/api-client';
import { formatBdt, formatDateTime } from '@/lib/format';

// Radix Select items can't have an empty value.
const NO_PROPERTY = 'none';

function inArea(property: Property, area: string): boolean {
  const key = area.trim().toLowerCase();
  return [property.neighborhood, property.city, property.address_line].some((part) =>
    part?.toLowerCase().includes(key)
  );
}

function propertyLabel(property: Property): string {
  const price = formatBdt(property.price);
  return `${property.title} — ${property.listing_type === 'rent' ? `${price}/month` : price}`;
}

function leadLabel(lead: Client): string {
  return lead.preferred_location
    ? `${lead.full_name} — ${lead.preferred_location}`
    : lead.full_name;
}

export default function BookingsPage() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [leads, setLeads] = useState<Client[]>([]);
  const [properties, setProperties] = useState<Property[]>([]);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [clientId, setClientId] = useState('');
  const [propertyId, setPropertyId] = useState(NO_PROPERTY);
  const [when, setWhen] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function load() {
    setError(null);
    api
      .bookings()
      .then(setBookings)
      .catch((err) => {
        setBookings([]);
        setError(err instanceof Error ? err.message : 'Could not load bookings.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  function openDialog() {
    setClientId('');
    setPropertyId(NO_PROPERTY);
    setWhen('');
    setFormError(null);
    setOptionsError(null);
    setDialogOpen(true);
    Promise.all([api.leads.list({ limit: 1000 }), api.properties.list({ limit: 1000 })])
      .then(([clients, listings]) => {
        setLeads([...clients].sort((a, b) => a.full_name.localeCompare(b.full_name)));
        setProperties(
          listings
            .filter((property) => property.is_active)
            .sort((a, b) => a.title.localeCompare(b.title))
        );
      })
      .catch((err) =>
        setOptionsError(err instanceof Error ? err.message : 'Could not load leads and listings.')
      );
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!clientId || !when) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await api.bookings.create({
        client_id: clientId,
        property_id: propertyId === NO_PROPERTY ? null : propertyId,
        proposed_datetime: new Date(when).toISOString(),
      });
      const lead = leads.find((client) => client.id === clientId);
      toast.success('Viewing booked', {
        description: `${lead?.full_name ?? 'Lead'}, ${formatDateTime(when)}`,
      });
      setDialogOpen(false);
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to book the viewing');
    } finally {
      setSubmitting(false);
    }
  }

  // The chosen lead's preferred area first, so the likely listing is near the top.
  const area = leads.find((client) => client.id === clientId)?.preferred_location ?? '';
  const propertyGroups = area
    ? [
        { label: `In ${area}`, rows: properties.filter((p) => inArea(p, area)) },
        { label: 'Other areas', rows: properties.filter((p) => !inArea(p, area)) },
      ]
    : [{ label: 'Listings', rows: properties }];

  return (
    <>
      <PageHeader
        title="Bookings"
        description="Viewings the agent arranged in chats and on calls, plus any you book here."
        actions={
          <Button onClick={openDialog}>
            <PlusIcon aria-hidden="true" />
            Add booking
          </Button>
        }
      />
      <Panel>
        {loading || error || bookings.length === 0 ? (
          <TableState
            loading={loading}
            error={error}
            onRetry={load}
            empty={
              <>
                <p className="text-foreground font-medium">No bookings yet</p>
                <p>
                  When a lead agrees to a viewing, the agent records it here, or add one yourself.
                </p>
              </>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Viewing time</TableHead>
                <TableHead>Client</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Booked through</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Booked on</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bookings.map((booking) => {
                const status = BOOKING_STATUS[booking.status] ?? {
                  label: booking.status,
                  tone: 'neutral' as const,
                };
                return (
                  <TableRow key={booking.id}>
                    <TableCell className="font-medium tabular-nums">
                      {formatDateTime(booking.proposed_datetime)}
                    </TableCell>
                    <TableCell>{booking.client_name ?? '—'}</TableCell>
                    <TableCell className="tabular-nums">
                      {booking.client_phone ? (
                        <a href={`tel:${booking.client_phone}`} className="hover:underline">
                          {booking.client_phone}
                        </a>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>{BOOKING_CHANNEL[booking.channel] ?? booking.channel}</TableCell>
                    <TableCell>
                      <StatusPill tone={status.tone}>{status.label}</StatusPill>
                    </TableCell>
                    <TableCell className="text-muted-foreground tabular-nums">
                      {formatDateTime(booking.created_at)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Panel>

      <Dialog open={dialogOpen} onOpenChange={(open) => !submitting && setDialogOpen(open)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add booking</DialogTitle>
            <DialogDescription>
              Book a viewing for a lead. A call scheduled for them before it follows it up.
            </DialogDescription>
          </DialogHeader>
          <form id="add-booking" onSubmit={handleCreate} className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="booking-client">Lead</Label>
              <Select value={clientId} onValueChange={setClientId} required>
                <SelectTrigger id="booking-client" className="w-full">
                  <SelectValue placeholder="Choose a lead" />
                </SelectTrigger>
                <SelectContent>
                  {leads.map((lead) => (
                    <SelectItem key={lead.id} value={lead.id}>
                      {leadLabel(lead)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="booking-property">Property</Label>
              <Select value={propertyId} onValueChange={setPropertyId}>
                <SelectTrigger id="booking-property" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_PROPERTY}>No specific property</SelectItem>
                  {propertyGroups
                    .filter((group) => group.rows.length > 0)
                    .map((group) => (
                      <SelectGroup key={group.label}>
                        <SelectLabel>{group.label}</SelectLabel>
                        {group.rows.map((property) => (
                          <SelectItem key={property.id} value={property.id}>
                            {propertyLabel(property)}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="booking-when">Viewing time</Label>
              <Input
                id="booking-when"
                type="datetime-local"
                value={when}
                onChange={(e) => setWhen(e.target.value)}
                required
              />
            </div>
            {(formError || optionsError) && (
              <p role="alert" className="text-destructive text-sm">
                {formError ?? optionsError}
              </p>
            )}
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form="add-booking" disabled={submitting || !clientId || !when}>
              {submitting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              {submitting ? 'Booking…' : 'Add booking'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
