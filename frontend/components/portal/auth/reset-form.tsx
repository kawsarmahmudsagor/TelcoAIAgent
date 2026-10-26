'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2Icon } from 'lucide-react';
import { CODE_LENGTH, CodeInput, emptyCode } from '@/components/portal/actions/code-input';
import { SmsCard } from '@/components/portal/actions/sms-toast';
import { AuthError, AuthLink } from '@/components/portal/auth/auth-shell';
import { Field, MsisdnField, PASSWORD_MAX, PASSWORD_MIN } from '@/components/portal/auth/fields';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api-client';
import { portalApi } from '@/lib/portal-api';
import type { ResetStart } from '@/lib/types/portal';

const START_ERRORS: Record<string, string> = {
  subscriber_not_found: 'No account uses that number. Check it, or create an account.',
  too_many_codes: 'Too many codes asked for. Wait a few minutes and try again.',
};

const CONFIRM_ERRORS: Record<string, string> = {
  otp_invalid: 'That code doesn’t match the SMS. Check it and try again.',
  otp_expired: 'That code has expired. Send a new one.',
  otp_attempts_exceeded: 'Too many wrong codes. Send a new one.',
  no_pending_action: 'That code is no longer valid. Send a new one.',
};

/**
 * Two steps: the number, which "sends" a code (shown on the page as an SMS, since the demo has
 * no SMS gateway), then the code and the new password, which signs the customer in.
 */
export function ResetForm({ next }: { next: string }) {
  const router = useRouter();
  const [msisdn, setMsisdn] = useState('');
  const [start, setStart] = useState<ResetStart | null>(null);
  const [smsVisible, setSmsVisible] = useState(false);
  const [digits, setDigits] = useState(emptyCode);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function failure(err: unknown, messages: Record<string, string>, fallback: string) {
    setError(
      err instanceof ApiError && err.code && messages[err.code] ? messages[err.code] : fallback
    );
    setSubmitting(false);
  }

  async function sendCode(e?: React.FormEvent) {
    e?.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      setStart(await portalApi.resetStart(msisdn));
      setSmsVisible(true);
      setDigits(emptyCode());
      setSubmitting(false);
    } catch (err) {
      failure(err, START_ERRORS, 'The code wasn’t sent. Check your connection and try again.');
    }
  }

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    if (!start) return;
    setError(null);
    setSubmitting(true);
    try {
      await portalApi.resetConfirm({
        msisdn,
        reset_id: start.reset_id,
        code: digits.join(''),
        new_password: password,
      });
      router.push(next);
    } catch (err) {
      failure(err, CONFIRM_ERRORS, 'The password wasn’t changed. Try again.');
    }
  }

  const card = 'border-line bg-surface rounded-panel shadow-panel flex flex-col gap-5 border p-6';

  if (!start) {
    return (
      <form onSubmit={sendCode} className={card}>
        <MsisdnField id="reset-msisdn" value={msisdn} onChange={setMsisdn} autoFocus />
        {error && <AuthError id="reset-error">{error}</AuthError>}
        <Button type="submit" size="lg" disabled={submitting}>
          {submitting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
          {submitting ? 'Sending code…' : 'Send code'}
        </Button>
        <p className="text-muted-foreground text-sm">
          Remembered it?{' '}
          <AuthLink href={`/signin?next=${encodeURIComponent(next)}`}>Log in</AuthLink>
        </p>
      </form>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {smsVisible && (
        <SmsCard
          code={start.otp.code}
          to={start.otp.to}
          expiresAt={start.otp.expires_at}
          onDismiss={() => setSmsVisible(false)}
        />
      )}
      <form onSubmit={confirm} className={card}>
        <div className="grid gap-2">
          <p id="reset-code-label" className="text-sm leading-none font-medium">
            Code sent to {start.otp.to}
          </p>
          <CodeInput
            digits={digits}
            onChange={setDigits}
            labelledBy="reset-code-label"
            invalid={error !== null}
          />
        </div>
        <Field
          id="reset-password"
          label="New password"
          hint={`At least ${PASSWORD_MIN} characters.`}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          minLength={PASSWORD_MIN}
          maxLength={PASSWORD_MAX}
          required
        />
        {error && <AuthError id="reset-error">{error}</AuthError>}
        <Button
          type="submit"
          size="lg"
          disabled={submitting || digits.join('').length < CODE_LENGTH}
        >
          {submitting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
          {submitting ? 'Saving…' : 'Set password and log in'}
        </Button>
        <p className="text-muted-foreground flex flex-wrap justify-between gap-2 text-sm">
          <button
            type="button"
            onClick={() => void sendCode()}
            disabled={submitting}
            className="text-primary focus-visible:ring-ring/60 rounded-sm font-semibold underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] disabled:opacity-50"
          >
            Send a new code
          </button>
          <button
            type="button"
            onClick={() => {
              setStart(null);
              setError(null);
            }}
            className="focus-visible:ring-ring/60 rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-[3px]"
          >
            Use a different number
          </button>
        </p>
      </form>
    </div>
  );
}
