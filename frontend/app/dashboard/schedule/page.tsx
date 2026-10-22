'use client';

import { useEffect, useState } from 'react';
import { Loader2Icon, PhoneOffIcon, Trash2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { PageHeader } from '@/components/dashboard/page-header';
import { StatusPill } from '@/components/dashboard/status-pill';
import { CALL_STATUS } from '@/components/dashboard/status-tones';
import { Panel, TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
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
import { type CallScheduleEntry, type CallStatus, type ScheduleLead, api } from '@/lib/api-client';
import { formatDateTime, formatWeekdayDateTime } from '@/lib/format';

// Ringing or connected -- a phone call in these states can be hung up.
const LIVE_STATUSES = new Set<CallStatus>(['dispatched', 'in_progress']);
// Not finished yet -- the call's type (cold or follow-up) is still worth showing.
const OPEN_STATUSES = new Set<CallStatus>(['pending', 'dispatched', 'in_progress']);

/**
 * "Name — Property title, Wed 14 Oct 10:00", "Name — viewing …" without a property, or just the
 * name (with their area) for a lead with no viewing coming up.
 */
function leadLabel({ client, viewing }: ScheduleLead): string {
  if (!viewing) {
    return client.preferred_location
      ? `${client.full_name} — ${client.preferred_location}`
      : client.full_name;
  }
  const when = formatWeekdayDateTime(viewing.when);
  return viewing.property_title
    ? `${client.full_name} — ${viewing.property_title}, ${when}`
    : `${client.full_name} — viewing ${when}`;
}

/**
 * Whether an open call will follow up a booked viewing or be a cold call, as things stand now
 * (the agent decides again when the call starts). Finished calls show a dash.
 */
function CallType({ entry }: { entry: CallScheduleEntry }) {
  if (!OPEN_STATUSES.has(entry.status)) {
    return <span className="text-muted-foreground">—</span>;
  }
  const { viewing } = entry;
  if (!viewing) {
    return <StatusPill tone="neutral">Cold call</StatusPill>;
  }
  const when = formatWeekdayDateTime(viewing.when);
  const detail = viewing.property_title ? `${viewing.property_title}, ${when}` : `Viewing ${when}`;
  return (
    <div className="grid gap-1">
      <StatusPill tone="info" className="w-fit">
        Follow-up
      </StatusPill>
      <span className="text-muted-foreground truncate text-xs" title={detail}>
        {detail}
      </span>
    </div>
  );
}

export default function SchedulePage() {
  const [entries, setEntries] = useState<CallScheduleEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [leads, setLeads] = useState<ScheduleLead[]>([]);
  const [leadsLoaded, setLeadsLoaded] = useState(false);
  const [leadsError, setLeadsError] = useState<string | null>(null);
  const [clientId, setClientId] = useState('');
  const [scheduledAt, setScheduledAt] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmEntry, setConfirmEntry] = useState<CallScheduleEntry | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [hangingUpId, setHangingUpId] = useState<string | null>(null);

  function loadEntries() {
    setLoadError(null);
    api
      .schedule()
      .then(setEntries)
      .catch((err) => {
        setEntries([]);
        setLoadError(err instanceof Error ? err.message : 'Could not load the call schedule.');
      })
      .finally(() => setLoading(false));
  }

  function loadLeads() {
    api.schedule
      .leads()
      .then((rows) => {
        setLeads(rows);
        setLeadsError(null);
      })
      .catch((err) => {
        setLeads([]);
        setLeadsError(err instanceof Error ? err.message : 'Could not load leads.');
      })
      .finally(() => setLeadsLoaded(true));
  }

  useEffect(() => {
    loadEntries();
    loadLeads();
    // Leads and viewings are added on calls and other pages while this one sits open:
    // refetch when the admin comes back to it (a new viewing can turn a cold call into
    // a follow-up).
    function refresh() {
      loadEntries();
      loadLeads();
    }
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!clientId || !scheduledAt) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createSchedule({
        client_id: clientId,
        scheduled_at: new Date(scheduledAt).toISOString(),
      });
      toast.success('Call scheduled', { description: formatDateTime(scheduledAt) });
      setClientId('');
      setScheduledAt('');
      loadEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to schedule call');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(entryId: string) {
    setDeletingId(entryId);
    try {
      await api.deleteSchedule(entryId);
      toast.success('Call deleted');
      setConfirmEntry(null);
      loadEntries();
    } catch (err) {
      toast.error('Could not delete the call', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setDeletingId(null);
    }
  }

  async function handleHangUp(entryId: string) {
    setHangingUpId(entryId);
    try {
      await api.hangUpCall(entryId);
      toast.success('Call hung up');
      loadEntries();
    } catch (err) {
      toast.error('Could not hang up', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setHangingUpId(null);
    }
  }

  // Loaded fine but there are no leads at all -- distinct from a failed fetch.
  const noLeads = leadsLoaded && leadsError === null && leads.length === 0;

  return (
    <>
      <PageHeader
        title="Call schedule"
        description="The agent calls any lead at the time you set, on this browser's incoming-call screen. A lead with a booked viewing gets a call that follows it up; any other lead gets a cold introduction call."
      />

      <Panel className="mb-6">
        <form
          onSubmit={handleSubmit}
          className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto] lg:items-end"
        >
          <div className="grid gap-2">
            <Label htmlFor="call-client">Lead</Label>
            <Select
              value={clientId}
              onValueChange={setClientId}
              onOpenChange={(open) => open && loadLeads()}
              disabled={noLeads || leadsError !== null}
              required
            >
              <SelectTrigger id="call-client" className="w-full">
                <SelectValue placeholder={noLeads ? 'No leads yet' : 'Choose a lead'} />
              </SelectTrigger>
              <SelectContent>
                {[
                  { label: 'Viewing booked', rows: leads.filter((lead) => lead.viewing) },
                  { label: 'Other leads', rows: leads.filter((lead) => !lead.viewing) },
                ]
                  .filter((group) => group.rows.length > 0)
                  .map((group) => (
                    <SelectGroup key={group.label}>
                      <SelectLabel>{group.label}</SelectLabel>
                      {group.rows.map((lead) => (
                        <SelectItem key={lead.client.id} value={lead.client.id}>
                          {leadLabel(lead)}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ))}
              </SelectContent>
            </Select>
            {leadsError && (
              <p role="alert" className="text-destructive text-sm">
                Could not load leads: {leadsError}
              </p>
            )}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="call-time">Call time</Label>
            <Input
              id="call-time"
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              required
            />
          </div>
          <Button type="submit" disabled={submitting || !clientId || !scheduledAt}>
            {submitting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            {submitting ? 'Scheduling…' : 'Schedule call'}
          </Button>
          {error && (
            <p role="alert" className="text-destructive text-sm sm:col-span-2 lg:col-span-3">
              {error}
            </p>
          )}
        </form>
      </Panel>

      <Panel>
        {loading || loadError || entries.length === 0 ? (
          <TableState
            loading={loading}
            error={loadError}
            onRetry={loadEntries}
            empty={
              <>
                <p className="text-foreground font-medium">No calls scheduled</p>
                <p>Pick a lead and a time above to have the agent call them.</p>
              </>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Lead</TableHead>
                <TableHead>Call type</TableHead>
                <TableHead>Scheduled for</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Rings on</TableHead>
                <TableHead>Room</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => {
                // The scheduler always names the room `coldcall-{entry.id}`, deterministically,
                // and creates it the moment it dispatches -- so we can link to the listen page
                // right away, before `livekit_room_name` is even set, letting you have it open
                // and connected *before* the scheduled time hits (the agent now waits for a
                // participant to join before it starts talking).
                const roomName = entry.livekit_room_name ?? `coldcall-${entry.id}`;
                const status = CALL_STATUS[entry.status] ?? {
                  label: entry.status,
                  tone: 'neutral' as const,
                };
                return (
                  <TableRow key={entry.id}>
                    <TableCell className="font-medium">{entry.client.full_name}</TableCell>
                    <TableCell className="max-w-[14rem]">
                      <CallType entry={entry} />
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {formatDateTime(entry.scheduled_at)}
                    </TableCell>
                    <TableCell>
                      <StatusPill tone={status.tone} pulse={status.pulse}>
                        {status.label}
                      </StatusPill>
                    </TableCell>
                    <TableCell>
                      {entry.dial_number ? (
                        <span className="tabular-nums">{entry.dial_number}</span>
                      ) : (
                        <span className="text-muted-foreground">This browser</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <a
                        href={`/dashboard/listen?room=${encodeURIComponent(roomName)}`}
                        className="text-primary font-mono text-xs underline-offset-4 hover:underline"
                        title="Listen in on this call"
                      >
                        {roomName}
                      </a>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-[16rem] truncate">
                      {entry.outcome ?? '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        {entry.dial_number && LIVE_STATUSES.has(entry.status) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleHangUp(entry.id)}
                            disabled={hangingUpId === entry.id}
                            className="text-destructive hover:text-destructive"
                          >
                            {hangingUpId === entry.id ? (
                              <Loader2Icon className="animate-spin" aria-hidden="true" />
                            ) : (
                              <PhoneOffIcon aria-hidden="true" />
                            )}
                            Hang up
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => setConfirmEntry(entry)}
                          disabled={deletingId === entry.id}
                          aria-label={`Delete call with ${entry.client.full_name}`}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2Icon aria-hidden="true" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Panel>

      <ConfirmDialog
        open={confirmEntry !== null}
        onOpenChange={(open) => !open && setConfirmEntry(null)}
        title="Delete this scheduled call?"
        description={
          confirmEntry && (
            <>
              This removes the call to {confirmEntry.client.full_name} scheduled for{' '}
              {formatDateTime(confirmEntry.scheduled_at)}. This can&apos;t be undone.
            </>
          )
        }
        confirmLabel="Delete call"
        busy={deletingId !== null}
        onConfirm={() => (confirmEntry ? handleDelete(confirmEntry.id) : undefined)}
      />
    </>
  );
}
