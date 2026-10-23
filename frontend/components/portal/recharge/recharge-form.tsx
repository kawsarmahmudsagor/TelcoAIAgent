'use client';

import { useId, useState } from 'react';
import { ArrowUpRightIcon, Loader2Icon } from 'lucide-react';
import { type PayOption, PayOptions } from '@/components/portal/actions/pay-options';
import { usePortalAction } from '@/components/portal/actions/use-portal-action';
import { usePortalMe } from '@/components/portal/portal-me-context';
import { PortalButton } from '@/components/portal/ui/link-button';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { cn } from '@/lib/shadcn/utils';
import { formatTaka } from '@/lib/telco-format';
import type { TxnChannel } from '@/lib/types/portal';

/** Same rule as the backend (`app.bss.recharge`). */
const MSISDN = /^01[3-9]\d{8}$/;
const MIN = 20;
const MAX = 1000;
const CHIPS = [100, 200, 300, 500];
const DEFAULT_CHIP = 200;

const CHANNELS: PayOption[] = [
  { value: 'bkash', label: 'bKash' },
  { value: 'nagad', label: 'Nagad' },
  { value: 'card', label: 'Card' },
];

/** Digits only, and a leading 88 country code dropped ("+880 1712-342841" → "01712342841"). */
function normaliseMsisdn(raw: string): string {
  const digits = raw.replace(/\D/g, '');
  return digits.length === 13 && digits.startsWith('880') ? digits.slice(2) : digits;
}

/** The custom amount as a number, or the reason it can't be used. */
function parseAmount(raw: string): { amount?: number; error?: string } {
  const text = raw.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return { error: 'Enter an amount in taka, like 150.' };
  const amount = Number(text);
  if (amount < MIN || amount > MAX) {
    return { error: `Enter between ${formatTaka(MIN)} and ${formatTaka(MAX)}.` };
  }
  return { amount };
}

const FIELD =
  'bg-surface border-line text-foreground rounded-[9px] focus-visible:border-brand focus-visible:ring-ring/40 w-full border p-3 text-[13px] outline-none focus-visible:ring-[3px] aria-invalid:border-status-failed-foreground';

/**
 * "Make a recharge" (prepaid) or "Pay your bill" (postpaid, prefilled with the amount due):
 * number, amount, payment method, then the OTP flow.
 */
export function RechargeForm() {
  const me = usePortalMe();
  const postpaid = me.plan_type === 'postpaid';
  const summary = usePortalQuery('summary', portalApi.summary);
  const { start, dialog } = usePortalAction();
  const ids = useId();

  const due = postpaid ? (summary.data?.postpaid_due ?? 0) : 0;
  const billPrefill = due > 0 ? String(Math.round(Math.min(due, MAX) * 100) / 100) : null;

  const [msisdn, setMsisdn] = useState(me.msisdn);
  // `undefined` until the customer picks: then a bill's due amount, otherwise the default chip.
  const [chip, setChip] = useState<number | null | undefined>(undefined);
  const [custom, setCustom] = useState<string | undefined>(undefined);
  const [channel, setChannel] = useState<TxnChannel>('bkash');
  const [touched, setTouched] = useState({ msisdn: false, amount: false });
  const [sending, setSending] = useState(false);

  const customText = custom ?? (chip === undefined && billPrefill ? billPrefill : '');
  const selectedChip = chip === undefined ? (billPrefill ? null : DEFAULT_CHIP) : chip;

  const number = normaliseMsisdn(msisdn);
  const numberError = MSISDN.test(number)
    ? undefined
    : 'Enter an 11-digit mobile number starting 013–019.';
  const parsed = customText ? parseAmount(customText) : { amount: selectedChip ?? undefined };
  const amountError =
    parsed.error ?? (parsed.amount === undefined ? 'Pick or enter an amount.' : undefined);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched({ msisdn: true, amount: true });
    if (numberError || amountError || parsed.amount === undefined || sending) return;
    setSending(true);
    await start({
      kind: 'recharge',
      amount: parsed.amount,
      channel,
      ...(number === me.msisdn ? {} : { target_msisdn: number }),
    });
    setSending(false);
  }

  const showNumberError = touched.msisdn && numberError;
  const showAmountError = touched.amount && amountError;

  return (
    <>
      <form
        onSubmit={submit}
        noValidate
        className="bg-surface border-line rounded-panel shadow-panel phone:p-[18px] min-w-0 border p-6"
      >
        <h2 className="text-sm font-extrabold tracking-[-0.2px]">
          {postpaid ? 'Pay your bill' : 'Make a recharge'}
        </h2>
        <p className="text-muted-foreground mt-1 text-[11px]">
          {postpaid
            ? summary.data
              ? due > 0
                ? `Your bill is ${formatTaka(due)}. Pay up to ${formatTaka(MAX)} at a time.`
                : 'Your bill is fully paid. You can still pay ahead.'
              : 'Loading your bill…'
            : 'Recharge your telco. number or someone else’s.'}
        </p>

        <label htmlFor={`${ids}-msisdn`} className="mt-4 mb-[7px] block text-[11px] font-bold">
          Mobile number
        </label>
        <input
          id={`${ids}-msisdn`}
          className={FIELD}
          value={msisdn}
          onChange={(e) => setMsisdn(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, msisdn: true }))}
          inputMode="tel"
          autoComplete="tel-national"
          placeholder="01XXXXXXXXX"
          aria-invalid={showNumberError ? true : undefined}
          aria-describedby={showNumberError ? `${ids}-msisdn-error` : undefined}
        />
        {showNumberError && (
          <p
            id={`${ids}-msisdn-error`}
            className="text-status-failed-foreground mt-1.5 text-[11px]"
          >
            {numberError}
          </p>
        )}

        <fieldset className="mt-4">
          <legend className="mb-[7px] block text-[11px] font-bold">Choose amount</legend>
          <div className="phone:grid-cols-2 grid grid-cols-4 gap-2">
            {CHIPS.map((value) => {
              const selected = !customText && selectedChip === value;
              return (
                <label
                  key={value}
                  className={cn(
                    'rounded-button bg-surface border-line has-focus-visible:ring-ring/60 grid min-h-11 cursor-pointer place-items-center border px-1 py-3 text-sm font-extrabold has-focus-visible:ring-[3px]',
                    selected && 'border-brand text-brand-text bg-tint-selected'
                  )}
                >
                  <input
                    type="radio"
                    name={`${ids}-amount`}
                    className="sr-only"
                    checked={selected}
                    onChange={() => {
                      setChip(value);
                      setCustom('');
                    }}
                  />
                  ৳{value}
                </label>
              );
            })}
          </div>
        </fieldset>

        <label htmlFor={`${ids}-custom`} className="mt-4 mb-[7px] block text-[11px] font-bold">
          {postpaid ? 'Amount to pay (৳)' : 'Or enter a custom amount (৳)'}
        </label>
        <input
          id={`${ids}-custom`}
          className={FIELD}
          value={customText}
          onChange={(e) => {
            setCustom(e.target.value);
            setChip(null);
          }}
          onBlur={() => setTouched((t) => ({ ...t, amount: true }))}
          inputMode="decimal"
          placeholder={`${MIN}–${MAX}`}
          aria-invalid={showAmountError ? true : undefined}
          aria-describedby={`${ids}-amount-hint`}
        />
        <p
          id={`${ids}-amount-hint`}
          className={cn(
            'mt-1.5 text-[11px]',
            showAmountError ? 'text-status-failed-foreground' : 'text-muted-foreground'
          )}
        >
          {showAmountError || `${formatTaka(MIN)} to ${formatTaka(MAX)} per recharge.`}
        </p>

        <PayOptions
          className="mt-4"
          name={`${ids}-channel`}
          legend="Payment method"
          options={CHANNELS}
          value={channel}
          onChange={setChannel}
        />

        <PortalButton
          type="submit"
          disabled={sending}
          className="mt-[22px] min-h-11 w-full py-[13px]"
        >
          {sending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
          {sending ? 'Sending your code…' : 'Continue to payment'}
          {!sending && <ArrowUpRightIcon aria-hidden="true" />}
        </PortalButton>
        <p className="text-muted-foreground mt-3 text-[10px]">
          Demo only — no real payment will be processed.
        </p>
      </form>
      {/* Outside the form: React events bubble through portals, so the dialog's submit would
        reach this form's onSubmit. */}
      {dialog}
    </>
  );
}
