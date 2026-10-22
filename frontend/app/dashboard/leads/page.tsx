'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2Icon, PlusIcon, UploadIcon } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/dashboard/page-header';
import { StatusPill } from '@/components/dashboard/status-pill';
import { LEAD_STATUS } from '@/components/dashboard/status-tones';
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
import { type Client, api } from '@/lib/api-client';
import { formatBudget } from '@/lib/format';

const EMPTY_FORM = {
  full_name: '',
  phone: '',
  email: '',
  preferred_location: '',
  preferred_property_type: '',
  budget_min: '',
  budget_max: '',
  rent_or_buy: 'undecided' as 'rent' | 'buy' | 'undecided',
};

const RENT_OR_BUY = { rent: 'Rent', buy: 'Buy', undecided: 'Undecided' } as const;

export default function LeadsPage() {
  const [leads, setLeads] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  // `#lead-<id>` (linked from a conversation): scroll to that row and mark it.
  const [highlighted, setHighlighted] = useState<string | null>(null);

  function refresh() {
    setLoadError(null);
    api
      .leads()
      .then(setLeads)
      .catch((err) => {
        setLeads([]);
        setLoadError(err instanceof Error ? err.message : 'Could not load leads.');
      })
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  useEffect(() => {
    const hash = window.location.hash;
    if (loading || !hash.startsWith('#lead-')) return;
    const id = hash.slice('#lead-'.length);
    setHighlighted(id);
    document.getElementById(`lead-${id}`)?.scrollIntoView({ block: 'center' });
  }, [loading]);

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const result = await api.importClients(file);
      toast.success(`Imported ${result.imported} leads`, {
        description: result.skipped ? `${result.skipped} rows were skipped.` : undefined,
      });
      refresh();
    } catch (err) {
      toast.error('Import failed', {
        description: err instanceof Error ? err.message : 'Check the file is an .xlsx export.',
      });
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.full_name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createLead({
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || undefined,
        email: form.email.trim() || undefined,
        preferred_location: form.preferred_location.trim() || undefined,
        preferred_property_type: form.preferred_property_type.trim() || undefined,
        budget_min: form.budget_min ? Number(form.budget_min) : undefined,
        budget_max: form.budget_max ? Number(form.budget_max) : undefined,
        rent_or_buy: form.rent_or_buy,
      });
      toast.success('Lead added', { description: form.full_name.trim() });
      setForm(EMPTY_FORM);
      setDialogOpen(false);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create lead');
    } finally {
      setSubmitting(false);
    }
  }

  function field(key: keyof typeof EMPTY_FORM) {
    return {
      id: `lead-${key}`,
      value: form[key],
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm({ ...form, [key]: e.target.value }),
    };
  }

  return (
    <>
      <PageHeader
        title="Leads"
        description="People who enquired through the agent, plus anyone you add or import."
        actions={
          <>
            <input
              ref={fileInput}
              type="file"
              accept=".xlsx"
              onChange={handleImport}
              className="hidden"
            />
            <Button
              variant="outline"
              onClick={() => fileInput.current?.click()}
              disabled={importing}
            >
              {importing ? (
                <Loader2Icon className="animate-spin" aria-hidden="true" />
              ) : (
                <UploadIcon aria-hidden="true" />
              )}
              Import from Excel
            </Button>
            <Button onClick={() => setDialogOpen(true)}>
              <PlusIcon aria-hidden="true" />
              Add lead
            </Button>
          </>
        }
      />

      <Panel>
        {loading || loadError || leads.length === 0 ? (
          <TableState
            loading={loading}
            error={loadError}
            onRetry={refresh}
            empty={
              <>
                <p className="text-foreground font-medium">No leads yet</p>
                <p>Leads appear here when the agent books a viewing, or add one yourself.</p>
              </>
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Budget</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Rent or buy</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {leads.map((lead) => {
                const status = LEAD_STATUS[lead.lead_status];
                return (
                  <TableRow
                    key={lead.id}
                    id={`lead-${lead.id}`}
                    data-state={highlighted === lead.id ? 'selected' : undefined}
                  >
                    <TableCell className="font-medium">{lead.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {lead.email ?? lead.phone ?? '—'}
                    </TableCell>
                    <TableCell>
                      <StatusPill tone={status?.tone ?? 'neutral'}>
                        {status?.label ?? lead.lead_status}
                      </StatusPill>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {formatBudget(lead.budget_min, lead.budget_max)}
                    </TableCell>
                    <TableCell>{lead.preferred_location ?? '—'}</TableCell>
                    <TableCell>{RENT_OR_BUY[lead.rent_or_buy] ?? lead.rent_or_buy}</TableCell>
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
            <DialogTitle>Add lead</DialogTitle>
            <DialogDescription>Only the name is required.</DialogDescription>
          </DialogHeader>
          <form id="add-lead" onSubmit={handleCreate} className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2 sm:col-span-2">
              <Label htmlFor="lead-full_name">Name</Label>
              <Input {...field('full_name')} required autoFocus />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lead-phone">Phone</Label>
              <Input {...field('phone')} type="tel" placeholder="+8801XXXXXXXXX" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lead-email">Email</Label>
              <Input {...field('email')} type="email" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lead-preferred_location">Preferred area</Label>
              <Input {...field('preferred_location')} placeholder="Gulshan, Banani…" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lead-preferred_property_type">Property type</Label>
              <Input {...field('preferred_property_type')} placeholder="Apartment, duplex…" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lead-budget_min">Budget from (৳)</Label>
              <Input {...field('budget_min')} type="number" min={0} inputMode="numeric" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lead-budget_max">Budget up to (৳)</Label>
              <Input {...field('budget_max')} type="number" min={0} inputMode="numeric" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lead-rent_or_buy">Rent or buy</Label>
              <Select
                value={form.rent_or_buy}
                onValueChange={(value) =>
                  setForm({ ...form, rent_or_buy: value as typeof form.rent_or_buy })
                }
              >
                <SelectTrigger id="lead-rent_or_buy" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="undecided">Undecided</SelectItem>
                  <SelectItem value="rent">Rent</SelectItem>
                  <SelectItem value="buy">Buy</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {error && (
              <p role="alert" className="text-destructive text-sm sm:col-span-2">
                {error}
              </p>
            )}
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" form="add-lead" disabled={submitting}>
              {submitting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              {submitting ? 'Adding…' : 'Add lead'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
