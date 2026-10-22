'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { CheckIcon, Loader2Icon, ShieldCheckIcon, TimerOffIcon, XIcon } from 'lucide-react';
import { useMaybeRoomContext, useVoiceAssistant } from '@livekit/components-react';
import { CodeInput, type CodeInputHandle, emptyCode } from '@/components/portal/actions/code-input';
import { payFromLabel } from '@/components/portal/actions/otp-dialog';
import { useCountdown } from '@/components/portal/actions/use-countdown';
import { useOptionalPortalMe } from '@/components/portal/portal-me-context';
import { PortalButton } from '@/components/portal/ui/link-button';
import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import { cn } from '@/lib/shadcn/utils';
import { formatTaka } from '@/lib/telco-format';
import { type ConfirmState, TELCO_RPC } from '@/lib/telco-topics';
import type { PortalActionKind } from '@/lib/types/portal';

const HEADINGS: Record<PortalActionKind, Record<ConfirmState['state'], string>> = {
  purchase: {
    awaiting_code: 'Confirm purchase',
    done: 'Pack activated',
    cancelled: 'Purchase cancelled',
    expired: 'Purchase expired',
  },
  recharge: {
    awaiting_code: 'Confirm recharge',
    done: 'Recharge successful',
    cancelled: 'Recharge cancelled',
    expired: 'Recharge expired',
  },
  redeem: {
    awaiting_code: 'Confirm redemption',
    done: 'Reward redeemed',
    cancelled: 'Redemption cancelled',
    expired: 'Redemption expired',
  },
};

const SETTLED: Record<Exclude<ConfirmState['state'], 'awaiting_code'>, [StatusTone, string]> = {
  done: ['success', 'Done'],
  cancelled: ['failed', 'Cancelled'],
  expired: ['pending', 'Expired'],
};

interface RpcReply {
  ok: boolean;
  error: string | null;
}

/**
 * The agent's confirm card: what is being bought, recharged or redeemed, a countdown and the
 * 6-box code. Confirm and Cancel go to the agent over RPC; the agent answers on `telco.confirm`
 * with the new state, which turns the card read-only (with the ref once done). The same code
 * can be said or typed in the chat instead.
 */
export function ConfirmCard({ confirm }: { confirm: ConfirmState }) {
  const room = useMaybeRoomContext();
  const { agent } = useVoiceAssistant();
  const me = useOptionalPortalMe();
  const plan = me?.plan_type ?? 'prepaid';
  const labelId = useId();
  const [digits, setDigits] = useState<string[]>(emptyCode);
  const [busy, setBusy] = useState<'confirm' | 'cancel' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const codeRef = useRef<CodeInputHandle>(null);
  const left = useCountdown(confirm.expires_at);

  const awaiting = confirm.state === 'awaiting_code';
  // The agent only reports expiry when someone tries the code; the card knows the clock.
  const expired = awaiting && left.expired;
  const complete = digits.every((d) => d !== '');
  const canConfirm = awaiting && complete && !busy && !expired;

  // A settled card has nothing left in flight.
  useEffect(() => {
    if (!awaiting) {
      setBusy(null);
      setError(null);
    }
  }, [awaiting]);

  async function call(method: string, payload: Record<string, unknown>): Promise<RpcReply> {
    if (!room || !agent) throw new Error('not connected');
    const reply = await room.localParticipant.performRpc({
      destinationIdentity: agent.identity,
      method,
      payload: JSON.stringify({ action_id: confirm.action_id, ...payload }),
    });
    return JSON.parse(reply) as RpcReply;
  }

  async function submit() {
    if (!canConfirm) return;
    setBusy('confirm');
    setError(null);
    try {
      const reply = await call(TELCO_RPC.confirm, { code: digits.join('') });
      if (!reply.ok) {
        setError(reply.error ?? 'That didn’t go through. Try again.');
        setDigits(emptyCode());
        codeRef.current?.focus(0);
      }
    } catch (err) {
      console.error('telco.confirm_action failed:', err);
      setError('The assistant didn’t answer. Check your connection and try again.');
    } finally {
      setBusy(null);
    }
  }

  async function cancel() {
    if (busy) return;
    setBusy('cancel');
    setError(null);
    try {
      const reply = await call(TELCO_RPC.cancel, {});
      if (!reply.ok) setError(reply.error ?? 'That didn’t go through. Try again.');
    } catch (err) {
      console.error('telco.cancel_action failed:', err);
      setError('The assistant didn’t answer. Check your connection and try again.');
    } finally {
      setBusy(null);
    }
  }

  const rows: [string, string][] = [];
  if (confirm.kind === 'redeem' || confirm.amount === null) {
    if (confirm.points != null)
      rows.push(['Points', `${confirm.points.toLocaleString('en-IN')} pts`]);
  } else {
    rows.push(['Amount', formatTaka(confirm.amount)]);
  }
  if (confirm.pay_from) rows.push(['Pay from', payFromLabel(confirm.pay_from, plan)]);
  if (confirm.target) rows.push(['To', confirm.target]);
  if (confirm.state === 'done' && confirm.ref) rows.push(['Ref', confirm.ref]);

  const Icon =
    confirm.state === 'done'
      ? CheckIcon
      : confirm.state === 'cancelled'
        ? XIcon
        : confirm.state === 'expired'
          ? TimerOffIcon
          : ShieldCheckIcon;
  const settled = awaiting ? null : SETTLED[confirm.state as keyof typeof SETTLED];

  return (
    <section
      aria-labelledby={`${labelId}-title`}
      className={cn(
        'bg-surface rounded-metric w-full max-w-[380px] border p-4 shadow-[0_10px_28px_#1822460f]',
        awaiting ? 'border-[#d8d5ff] dark:border-[#3a3775]' : 'border-line'
      )}
    >
      <div className="flex items-start gap-2.5">
        <span
          aria-hidden="true"
          className={cn(
            'grid size-9 shrink-0 place-items-center rounded-[11px] [&_svg]:size-[17px]',
            confirm.state === 'done'
              ? 'bg-tint-green text-mint'
              : awaiting
                ? 'bg-tint-purple text-brand dark:text-[#a9a3ff]'
                : 'bg-surface2 text-muted-foreground'
          )}
        >
          <Icon />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-muted-foreground text-[10px] font-bold">
            {HEADINGS[confirm.kind]?.[confirm.state] ?? confirm.title}
          </p>
          <h3
            id={`${labelId}-title`}
            className="truncate text-[15px] leading-snug font-extrabold tracking-[-0.3px]"
          >
            {confirm.title}
          </h3>
        </div>
        {settled ? (
          <StatusChip tone={settled[0]}>{settled[1]}</StatusChip>
        ) : (
          <span
            className={cn(
              'shrink-0 text-[11px] tabular-nums',
              expired
                ? 'text-status-failed-foreground font-bold'
                : left.seconds <= 30
                  ? 'text-status-pending-foreground font-bold'
                  : 'text-muted-foreground'
            )}
          >
            {expired ? 'Expired' : left.label}
          </span>
        )}
      </div>

      {rows.length > 0 && (
        <dl className="bg-surface2 border-line mt-3 rounded-xl border px-3 py-0.5">
          {rows.map(([term, value]) => (
            <div
              key={term}
              className="border-line flex items-center justify-between gap-3 border-b py-2 text-xs last:border-b-0"
            >
              <dt className="text-muted-foreground">{term}</dt>
              <dd className="truncate font-bold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {awaiting && (
        <form
          className="mt-3.5"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <p id={`${labelId}-code`} className="mb-2 text-[11px] font-bold">
            Enter the code from the SMS
          </p>
          <CodeInput
            ref={codeRef}
            digits={digits}
            onChange={setDigits}
            labelledBy={`${labelId}-code`}
            readOnly={busy !== null || expired}
            invalid={Boolean(error)}
            size="sm"
          />
          <div aria-live="polite" className="min-h-4">
            {error && (
              <p role="alert" className="text-status-failed-foreground mt-2 text-[11px] font-bold">
                {error}
              </p>
            )}
            {!error && expired && (
              <p className="text-muted-foreground mt-2 text-[11px]">
                The code expired. Cancel, then ask the assistant again for a new one.
              </p>
            )}
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <PortalButton variant="outline" onClick={() => void cancel()} disabled={busy !== null}>
              {busy === 'cancel' && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              Cancel
            </PortalButton>
            <PortalButton type="submit" disabled={!canConfirm} aria-busy={busy === 'confirm'}>
              {busy === 'confirm' && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              {busy === 'confirm' ? 'Confirming…' : 'Confirm'}
            </PortalButton>
          </div>
        </form>
      )}
    </section>
  );
}
