'use client';

import { XIcon } from 'lucide-react';
import { toast } from 'sonner';
import { useCountdown } from '@/components/portal/actions/use-countdown';

export interface SmsToastInput {
  code: string;
  /** The masked number the code was "sent" to. */
  to: string;
  /** ISO datetime the code stops working. */
  expiresAt: string;
}

/**
 * Shows the demo OTP as a phone SMS notification, bottom right. It stays until it is dismissed
 * or the code expires. Returns the toast id, so the caller can dismiss it once the code is used.
 */
export function showSmsToast({ code, to, expiresAt }: SmsToastInput): string | number {
  const duration = Math.max(1000, Date.parse(expiresAt) - Date.now());
  return toast.custom(
    (id) => (
      <SmsCard code={code} to={to} expiresAt={expiresAt} onDismiss={() => toast.dismiss(id)} />
    ),
    { duration, unstyled: true }
  );
}

function SmsCard({
  code,
  to,
  expiresAt,
  onDismiss,
}: SmsToastInput & {
  onDismiss(): void;
}) {
  const left = useCountdown(expiresAt);

  return (
    <div
      role="status"
      aria-label={`Text message to ${to}: telco. OTP ${code}`}
      className="bg-toast text-toast-foreground w-[min(340px,calc(100vw-32px))] rounded-[18px] p-3.5 shadow-[0_18px_44px_#0b102040] ring-1 ring-white/10"
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="from-brand-start to-mint grid size-[22px] shrink-0 place-items-center rounded-[7px] bg-linear-135 text-[11px] font-black text-white"
        >
          t
        </span>
        <p className="min-w-0 flex-1 truncate text-[11px] font-bold">
          Messages
          <span className="font-medium opacity-60"> · to {to}</span>
        </p>
        <span className="text-[10px] font-medium tabular-nums opacity-60">
          {left.expired ? 'expired' : left.label}
        </span>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss message"
          className="focus-visible:ring-brand-text -m-1 grid size-7 place-items-center rounded-full opacity-60 outline-none hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2"
        >
          <XIcon className="size-3.5" aria-hidden="true" />
        </button>
      </div>
      <p className="mt-2 pl-[30px] text-[13px] leading-snug">
        telco. OTP:{' '}
        <strong className="text-[15px] font-extrabold tracking-[0.12em] tabular-nums select-all">
          {code}
        </strong>{' '}
        — valid 3 min. Never share it.
      </p>
    </div>
  );
}
