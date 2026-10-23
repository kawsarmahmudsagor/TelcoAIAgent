'use client';

import { useId, useState } from 'react';
import { LifeBuoyIcon, Loader2Icon } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';
import { toast } from 'sonner';
import { PORTAL_CASE_CATEGORIES } from '@/components/portal/support/case-categories';
import { PortalButton } from '@/components/portal/ui/link-button';
import { ApiError } from '@/lib/api-client';
import { portalApi } from '@/lib/portal-api';
import { invalidatePortal } from '@/lib/portal-sync';
import { cn } from '@/lib/shadcn/utils';
import type { CasePriority, PortalCaseCategory } from '@/lib/types/portal';

const MIN = 10;
const MAX = 1000;

const FIELD =
  'bg-surface border-line text-foreground rounded-[9px] focus-visible:border-brand focus-visible:ring-ring/40 w-full border p-3 text-[13px] outline-none focus-visible:ring-[3px] aria-invalid:border-status-failed-foreground';

const PRIORITIES: [CasePriority, string][] = [
  ['normal', 'Normal'],
  ['high', 'High'],
];

/** The reference's modal, filing a new support case. */
export function NewCaseDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 fixed inset-0 z-50 bg-[#0b102077]" />
        {/* Mounted per opening, so each opening gets a fresh form and request id. */}
        {open && <CaseForm onClose={() => onOpenChange(false)} />}
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function CaseForm({ onClose }: { onClose(): void }) {
  const ids = useId();
  // One id per opening: a double submit (or a retry after a lost response) files one case.
  const [requestId] = useState(() => crypto.randomUUID());
  const [category, setCategory] = useState<PortalCaseCategory>('recharge_not_credited');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<CasePriority>('normal');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const length = description.trim().length;
  const invalid = length < MIN || length > MAX;
  const showInvalid = touched && invalid;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await portalApi.createCase({
        category,
        description: description.trim(),
        priority,
        request_id: requestId,
      });
      invalidatePortal(['cases', 'summary']);
      toast.success(`Case ${created.ref} created`);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the case. Try again.');
      setBusy(false);
    }
  }

  return (
    <DialogPrimitive.Content
      onEscapeKeyDown={(e) => busy && e.preventDefault()}
      onInteractOutside={(e) => e.preventDefault()}
      className="bg-surface border-line data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 phone:p-5 fixed top-1/2 left-1/2 z-[51] max-h-[calc(100dvh-32px)] w-[min(460px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[18px] border p-6 shadow-[0_25px_70px_#0003] outline-none"
    >
      <div className="mb-[7px] flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="bg-tint-purple text-brand grid size-9 shrink-0 place-items-center rounded-[11px] dark:text-[#a9a3ff]"
        >
          <LifeBuoyIcon className="size-[17px]" />
        </span>
        <DialogPrimitive.Title className="text-lg leading-tight font-bold tracking-[-0.3px]">
          New case
        </DialogPrimitive.Title>
      </div>
      <DialogPrimitive.Description className="text-muted-foreground mb-4 text-xs">
        Tell us what went wrong and our team will look into it.
      </DialogPrimitive.Description>

      <form onSubmit={submit} noValidate>
        <label htmlFor={`${ids}-category`} className="mb-[7px] block text-[11px] font-bold">
          Category
        </label>
        <select
          id={`${ids}-category`}
          className={FIELD}
          value={category}
          onChange={(e) => setCategory(e.target.value as PortalCaseCategory)}
          disabled={busy}
        >
          {PORTAL_CASE_CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>

        <label htmlFor={`${ids}-description`} className="mt-4 mb-[7px] block text-[11px] font-bold">
          What happened?
        </label>
        <textarea
          id={`${ids}-description`}
          className={cn(FIELD, 'min-h-28 resize-y')}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          onBlur={() => setTouched(true)}
          readOnly={busy}
          aria-invalid={showInvalid ? true : undefined}
          aria-describedby={`${ids}-hint`}
          placeholder="For example: I recharged ৳300 via bKash at 2 pm and my balance did not change."
        />
        <div className="mt-1.5 flex justify-between gap-3 text-[11px]">
          <p
            id={`${ids}-hint`}
            className={showInvalid ? 'text-status-failed-foreground' : 'text-muted-foreground'}
          >
            {length > MAX
              ? `Shorten this by ${length - MAX} characters.`
              : `Write at least ${MIN} characters.`}
          </p>
          <p
            className={cn(
              'tabular-nums',
              length > MAX ? 'text-status-failed-foreground' : 'text-muted-foreground'
            )}
          >
            {length}/{MAX}
          </p>
        </div>

        <fieldset className="mt-4" disabled={busy}>
          <legend className="mb-[7px] block text-[11px] font-bold">Priority</legend>
          <div className="grid grid-cols-2 gap-2">
            {PRIORITIES.map(([value, label]) => {
              const selected = priority === value;
              return (
                <label
                  key={value}
                  className={cn(
                    'rounded-button bg-surface border-line has-focus-visible:ring-ring/60 grid min-h-11 cursor-pointer place-items-center border px-1 py-2.5 text-xs font-extrabold has-focus-visible:ring-[3px]',
                    selected &&
                      'border-brand text-brand bg-tint-purple dark:bg-[#29274e] dark:text-[#a9a3ff]'
                  )}
                >
                  <input
                    type="radio"
                    name={`${ids}-priority`}
                    className="sr-only"
                    checked={selected}
                    onChange={() => setPriority(value)}
                  />
                  {label}
                </label>
              );
            })}
          </div>
        </fieldset>

        <div aria-live="polite" className="min-h-[18px]">
          {error && (
            <p role="alert" className="text-status-failed-foreground mt-2.5 text-[11px] font-bold">
              {error}
            </p>
          )}
        </div>

        <div className="mt-3.5 flex justify-end gap-2">
          <PortalButton variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </PortalButton>
          <PortalButton type="submit" disabled={busy} aria-busy={busy || undefined}>
            {busy && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            {busy ? 'Creating…' : 'Create case'}
          </PortalButton>
        </div>
      </form>
    </DialogPrimitive.Content>
  );
}
