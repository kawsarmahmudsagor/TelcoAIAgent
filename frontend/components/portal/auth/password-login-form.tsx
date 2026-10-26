'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2Icon } from 'lucide-react';
import { AuthError, AuthLink } from '@/components/portal/auth/auth-shell';
import { Field, MsisdnField } from '@/components/portal/auth/fields';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api-client';
import { portalApi } from '@/lib/portal-api';

/** Number + password sign-in for customers who signed up (or reset a password). */
export function PasswordLoginForm({ next }: { next: string }) {
  const router = useRouter();
  const [msisdn, setMsisdn] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const query = `?next=${encodeURIComponent(next)}`;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await portalApi.passwordLogin(msisdn, password);
      router.push(next);
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'invalid_credentials'
          ? 'That number and password don’t match. Check them and try again.'
          : 'Log in didn’t go through. Check your connection and try again.'
      );
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border-line bg-surface rounded-panel shadow-panel flex flex-col gap-5 border p-6"
    >
      <MsisdnField
        id="login-msisdn"
        value={msisdn}
        onChange={setMsisdn}
        autoFocus
        aria-invalid={error ? true : undefined}
      />
      <Field
        id="login-password"
        label="Password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
        required
        aria-invalid={error ? true : undefined}
      />

      {error && <AuthError id="login-error">{error}</AuthError>}

      <Button type="submit" size="lg" disabled={submitting}>
        {submitting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
        {submitting ? 'Logging in…' : 'Log in'}
      </Button>

      <p className="text-muted-foreground flex flex-wrap justify-between gap-2 text-sm">
        <span>
          New to telco.? <AuthLink href={`/signup${query}`}>Create an account</AuthLink>
        </span>
        <AuthLink href={`/reset${query}`}>Forgot password?</AuthLink>
      </p>
    </form>
  );
}
