'use client';

import { useRef, useState } from 'react';
import { Loader2Icon, ShieldCheckIcon } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';
import { CodeInput, type CodeInputHandle, emptyCode } from '@/components/portal/actions/code-input';
import { useCountdown } from '@/components/portal/actions/use-countdown';
import { usePortalMe } from '@/components/portal/portal-me-context';
import { PortalButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';
import { formatTaka } from '@/lib/telco-format';
import type { ActionStart, PlanType } from '@/lib/types/portal';

/** "Main balance" / "Add to bill" / "bKash" ... for the start's `pay_from`. */
export function payFromLabel(payFrom: string, plan: PlanType): string {
  switch (payFrom) {
    case 'balance':
      return plan === 'postpaid' ? 'Add to bill' : 'Main balance';
    case 'bkash':
      return 'bKash';
    case 'nagad':
      return 'Nagad';
    case 'card':
      return 'Card';
    case 'points':
      return 'Reward points';
    default:
      return payFrom;
  }
}

export interface OtpDialogProps {
  /** The started action; the dialog is open while this is set. */
  start: ActionStart | null;
  /** A confirm is in flight: Confirm and Cancel are disabled. */
  busy: boolean;
  /** Inline error under the code boxes (e.g. "Wrong code"). */
  error: string | null;
  /** Wrong codes left; at 0 the code is spent and Confirm is disabled. */
  attemptsLeft: number;
  /** Resolves `true` when the code was wrong, so the boxes clear for another try. */
  onConfirm(code: string): Promise<boolean>;
  onCancel(): void;
}

/** The reference's modal, asking for the 6-digit code the SMS toast shows. */
export function OtpDialog(props: OtpDialogProps) {
  const { start, busy, onCancel } = props;
  return (
    <DialogPrimitive.Root
      open={start !== null}
      onOpenChange={(open) => {
        if (!open && !busy) onCancel();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 bg-scrim fixed inset-0 z-50" />
        {start && <OtpContent key={start.action_id} {...props} start={start} />}
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function OtpContent({
  start,
  busy,
  error,
  attemptsLeft,
  onConfirm,
  onCancel,
}: OtpDialogProps & { start: ActionStart }) {
  const me = usePortalMe();
  const [digits, setDigits] = useState<string[]>(emptyCode);
  const codeRef = useRef<CodeInputHandle>(null);
  const left = useCountdown(start.otp.expires_at);

  const code = digits.join('');
  const complete = digits.every((d) => d !== '');
  const spent = attemptsLeft <= 0;
  const canConfirm = complete && !busy && !left.expired && !spent;

  async function submit() {
    if (!canConfirm) return;
    const wrong = await onConfirm(code);
    if (wrong) {
      setDigits(emptyCode());
      codeRef.current?.focus(0);
    }
  }

  const rows: [string, string][] = [];
  if (start.points_cost !== null) {
    rows.push(['Points', `${start.points_cost.toLocaleString('en-IN')} pts`]);
  } else if (start.amount !== null) {
    rows.push(['Amount', formatTaka(start.amount)]);
  }
  if (start.pay_from) rows.push(['Pay from', payFromLabel(start.pay_from, me.plan_type)]);
  if (start.target) rows.push(['To', start.target]);

  return (
    <DialogPrimitive.Content
      onOpenAutoFocus={(e) => {
        e.preventDefault();
        codeRef.current?.focus(0);
      }}
      onEscapeKeyDown={(e) => busy && e.preventDefault()}
      onInteractOutside={(e) => e.preventDefault()}
      className="bg-surface border-line data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 phone:p-5 fixed top-1/2 left-1/2 z-[51] w-[min(420px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-[18px] border p-6 shadow-[0_25px_70px_#0003] outline-none"
    >
      <div className="mb-[7px] flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="bg-tint-purple text-brand-text grid size-9 shrink-0 place-items-center rounded-[11px]"
        >
          <ShieldCheckIcon className="size-[17px]" />
        </span>
        <DialogPrimitive.Title className="min-w-0 text-lg leading-tight font-bold tracking-[-0.3px]">
          {start.title}
        </DialogPrimitive.Title>
      </div>
      <DialogPrimitive.Description className="text-muted-foreground mb-4 text-xs">
        Enter the 6-digit code we sent to {start.otp.to} to confirm.
      </DialogPrimitive.Description>

      {rows.length > 0 && (
        <dl className="bg-surface2 border-line mb-[18px] rounded-xl border px-3.5 py-1">
          {rows.map(([term, value]) => (
            <div
              key={term}
              className="border-line flex items-center justify-between gap-3 border-b py-2.5 text-xs last:border-b-0"
            >
              <dt className="text-muted-foreground">{term}</dt>
              <dd className="font-bold">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <p id="otp-label" className="text-[11px] font-bold">
            Verification code
          </p>
          <p
            className={cn(
              'text-[11px] tabular-nums',
              left.expired
                ? 'text-status-failed-foreground font-bold'
                : left.seconds <= 30
                  ? 'text-status-pending-foreground font-bold'
                  : 'text-muted-foreground'
            )}
          >
            {left.expired ? 'Code expired' : `Expires in ${left.label}`}
          </p>
        </div>
        <CodeInput
          ref={codeRef}
          digits={digits}
          onChange={setDigits}
          labelledBy="otp-label"
          readOnly={busy}
          invalid={Boolean(error)}
        />

        <div aria-live="polite" className="min-h-[18px]">
          {error && (
            <p role="alert" className="text-status-failed-foreground mt-2.5 text-[11px] font-bold">
              {error}
            </p>
          )}
          {!error && left.expired && (
            <p className="text-muted-foreground mt-2.5 text-[11px]">
              Cancel and start again for a new code.
            </p>
          )}
        </div>

        <div className="mt-[18px] flex justify-end gap-2">
          <PortalButton variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </PortalButton>
          <PortalButton type="submit" disabled={!canConfirm} aria-busy={busy || undefined}>
            {busy && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            {busy ? 'Confirming…' : 'Confirm'}
          </PortalButton>
        </div>
      </form>
    </DialogPrimitive.Content>
  );
}
