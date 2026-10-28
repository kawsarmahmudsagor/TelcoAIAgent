'use client';

import { type ReactNode, createElement, useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { OtpDialog } from '@/components/portal/actions/otp-dialog';
import { showSmsToast } from '@/components/portal/actions/sms-toast';
import { ApiError } from '@/lib/api-client';
import { portalApi } from '@/lib/portal-api';
import { signInHref } from '@/lib/portal-next';
import { invalidatePortal } from '@/lib/portal-sync';
import type { ActionStart, PortalAction } from '@/lib/types/portal';

/** `app.bss.otp.MAX_ATTEMPTS`: wrong codes allowed before the code locks. */
const MAX_ATTEMPTS = 3;

// Plainer words than the BSS defaults for what a customer can act on; anything else shows the
// backend's own message.
const FRIENDLY: Record<string, string> = {
  insufficient_balance:
    'Your main balance is too low for this. Recharge or pick another way to pay.',
  insufficient_points: 'You don’t have enough reward points for this offer yet.',
  offer_not_eligible: 'This offer isn’t available on your number.',
  otp_expired: 'The code expired. Start again to get a new one.',
  otp_attempts_exceeded: 'Too many wrong codes. Start again to get a new one.',
};

function asApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, 'The portal could not be reached. Check your connection and try again.');
}

const messageOf = (e: ApiError) => (e.code && FRIENDLY[e.code]) || e.message;

interface Pending {
  action: PortalAction;
  start: ActionStart;
  smsToast: string | number;
}

/**
 * The portal's OTP flow for a purchase, recharge or redemption. `start(action)` asks the backend
 * for a code, shows it as an SMS toast and opens the code dialog; Confirm sends the same action
 * back with the code. Render `dialog` once on the page. `start` never throws: failures are
 * toasted, and it resolves once the dialog is open (or the start failed).
 */
export function usePortalAction(): { start(a: PortalAction): Promise<void>; dialog: ReactNode } {
  const router = useRouter();
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wrongCodes, setWrongCodes] = useState(0);
  // Guards against a double click sending two confirms before `busy` re-renders.
  const inFlight = useRef(false);

  const onAuthLost = useCallback(
    (e: ApiError) => {
      if (e.status !== 401) return false;
      router.replace(signInHref(window.location.pathname + window.location.search));
      return true;
    },
    [router]
  );

  const close = useCallback((p: Pending | null) => {
    if (p) toast.dismiss(p.smsToast);
    setPending(null);
    setError(null);
    setWrongCodes(0);
  }, []);

  const start = useCallback(
    async (action: PortalAction) => {
      try {
        const started = await portalApi.startAction(action);
        const smsToast = showSmsToast({
          code: started.otp.code,
          to: started.otp.to,
          expiresAt: started.otp.expires_at,
        });
        setError(null);
        setWrongCodes(0);
        setPending({ action, start: started, smsToast });
      } catch (err) {
        const e = asApiError(err);
        if (onAuthLost(e)) return;
        if (e.code === 'too_many_codes') {
          toast.error('Too many codes — try again in a few minutes');
        } else {
          toast.error(messageOf(e));
        }
      }
    },
    [onAuthLost]
  );

  const confirm = useCallback(
    async (code: string): Promise<boolean> => {
      if (!pending || inFlight.current) return false;
      inFlight.current = true;
      setBusy(true);
      setError(null);
      try {
        const result = await portalApi.confirmAction(pending.start.action_id, pending.action, code);
        close(pending);
        toast.success(
          result.points_earned
            ? `Done — ref ${result.ref}. +${result.points_earned.toLocaleString('en-IN')} reward points`
            : `Done — ref ${result.ref}`
        );
        invalidatePortal();
        return false;
      } catch (err) {
        const e = asApiError(err);
        if (onAuthLost(e)) return false;
        if (e.code === 'otp_invalid') {
          const left = MAX_ATTEMPTS - (wrongCodes + 1);
          setWrongCodes(wrongCodes + 1);
          setError(
            left > 0
              ? `Wrong code. ${left} ${left === 1 ? 'attempt' : 'attempts'} left.`
              : 'Wrong code. No attempts left — cancel and start again for a new code.'
          );
          return true;
        }
        if (e.code === 'otp_expired' || e.code === 'otp_attempts_exceeded') {
          close(pending);
          toast.error(messageOf(e));
          return false;
        }
        setError(messageOf(e));
        return false;
      } finally {
        inFlight.current = false;
        setBusy(false);
      }
    },
    [pending, wrongCodes, close, onAuthLost]
  );

  const dialog = createElement(OtpDialog, {
    start: pending?.start ?? null,
    busy,
    error,
    attemptsLeft: MAX_ATTEMPTS - wrongCodes,
    onConfirm: confirm,
    onCancel: () => close(pending),
  });

  return { start, dialog };
}
