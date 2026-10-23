'use client';

import { useState } from 'react';
import { Loader2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { FormField, SELECT } from '@/components/dashboard/form-field';
import { SegmentedFilter } from '@/components/dashboard/list-controls';
import { KIND_LABEL } from '@/components/dashboard/network/incident-parts';
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
import { dhakaLocalToIso } from '@/lib/telco-format';
import type { IncidentKind } from '@/lib/types/portal';

const OTHER = '__other__';
type Status = 'investigating' | 'scheduled';

/** Declares an outage, congestion or maintenance window. Subscribers in the district see it in
 * their account and the assistant reports it. */
export function StageIncidentDialog({
  open,
  onOpenChange,
  districts,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  districts: string[];
}) {
  const [districtChoice, setDistrictChoice] = useState('');
  const [customDistrict, setCustomDistrict] = useState('');
  const [area, setArea] = useState('');
  const [kind, setKind] = useState<IncidentKind>('outage');
  const [status, setStatus] = useState<Status>('investigating');
  const [message, setMessage] = useState('');
  const [startsAt, setStartsAt] = useState('');
  const [endsAt, setEndsAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const district = (districtChoice === OTHER ? customDistrict : districtChoice).trim();
  const startsIso = dhakaLocalToIso(startsAt);
  const endsIso = dhakaLocalToIso(endsAt);
  const rangeError =
    startsIso && endsIso && endsIso <= startsIso ? 'The end must be after the start.' : null;
  const canSubmit = district && area.trim() && message.trim() && !rangeError;

  function reset() {
    setDistrictChoice('');
    setCustomDistrict('');
    setArea('');
    setKind('outage');
    setStatus('investigating');
    setMessage('');
    setStartsAt('');
    setEndsAt('');
    setError(null);
  }

  function close(next: boolean) {
    if (busy) return;
    onOpenChange(next);
    if (!next) reset();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await adminApi.createIncident({
        district,
        area: area.trim(),
        kind,
        status,
        message: message.trim(),
        starts_at: startsIso,
        ends_at: endsIso,
      });
      toast.success('Incident staged', { description: `${area.trim()}, ${district}` });
      invalidateAdmin(['network', 'overview']);
      onOpenChange(false);
      reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not stage the incident.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Stage incident</DialogTitle>
          <DialogDescription>
            Subscribers in the district see it, and the assistant reports it when asked about the
            network. Times are Bangladesh time; leave the start empty to begin now.
          </DialogDescription>
        </DialogHeader>
        <form id="stage-incident" onSubmit={submit} className="grid gap-4">
          <FormField id="inc-district" label="District">
            {(control) => (
              <select
                {...control}
                className={SELECT}
                value={districtChoice}
                onChange={(e) => setDistrictChoice(e.target.value)}
                required
              >
                <option value="" disabled>
                  Choose a district
                </option>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
                <option value={OTHER}>Another district…</option>
              </select>
            )}
          </FormField>
          {districtChoice === OTHER && (
            <FormField id="inc-district-custom" label="District name">
              {(control) => (
                <Input
                  {...control}
                  value={customDistrict}
                  onChange={(e) => setCustomDistrict(e.target.value)}
                  maxLength={60}
                  placeholder="e.g. Cumilla"
                />
              )}
            </FormField>
          )}
          <FormField id="inc-area" label="Area">
            {(control) => (
              <Input
                {...control}
                value={area}
                onChange={(e) => setArea(e.target.value)}
                maxLength={120}
                placeholder="e.g. Mirpur DOHS"
                required
              />
            )}
          </FormField>
          <div className="phone:grid-cols-1 grid grid-cols-2 gap-4">
            <FormField id="inc-kind" label="Kind">
              {(control) => (
                <select
                  {...control}
                  className={SELECT}
                  value={kind}
                  onChange={(e) => setKind(e.target.value as IncidentKind)}
                >
                  {(Object.keys(KIND_LABEL) as IncidentKind[]).map((k) => (
                    <option key={k} value={k}>
                      {KIND_LABEL[k]}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <div className="grid content-start gap-2">
              <span className="flex min-h-5 items-center text-sm leading-none font-medium">
                Status
              </span>
              <SegmentedFilter<Status>
                label="Status"
                value={status}
                onChange={setStatus}
                options={[
                  { value: 'investigating', label: 'Investigating' },
                  { value: 'scheduled', label: 'Scheduled' },
                ]}
              />
            </div>
          </div>
          <FormField id="inc-message" label="Message" hint="Shown to subscribers as written.">
            {(control) => (
              <Textarea
                {...control}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                maxLength={1000}
                required
              />
            )}
          </FormField>
          <div className="phone:grid-cols-1 grid grid-cols-2 gap-4">
            <FormField id="inc-starts" label="Starts" hint="Optional">
              {(control) => (
                <Input
                  {...control}
                  type="datetime-local"
                  value={startsAt}
                  onChange={(e) => setStartsAt(e.target.value)}
                />
              )}
            </FormField>
            <FormField id="inc-ends" label="Ends" hint="Optional" error={rangeError}>
              {(control) => (
                <Input
                  {...control}
                  type="datetime-local"
                  value={endsAt}
                  onChange={(e) => setEndsAt(e.target.value)}
                />
              )}
            </FormField>
          </div>
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="stage-incident" disabled={busy || !canSubmit}>
            {busy && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            Stage incident
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
