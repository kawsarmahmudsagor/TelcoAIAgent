'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2Icon } from 'lucide-react';
import { AuthError, AuthLink } from '@/components/portal/auth/auth-shell';
import { Field, MsisdnField, PASSWORD_MAX, PASSWORD_MIN } from '@/components/portal/auth/fields';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api-client';
import { portalApi } from '@/lib/portal-api';
import { cn } from '@/lib/shadcn/utils';
import type { PlanType } from '@/lib/types/portal';

const PLANS: { value: PlanType; label: string; hint: string }[] = [
  { value: 'prepaid', label: 'Prepaid', hint: 'Recharge as you go' },
  { value: 'postpaid', label: 'Postpaid', hint: 'Pay a monthly bill' },
];

/** Creates a customer account (FastAPI adds the welcome bonus), signs in and opens `next`. */
export function SignupForm({ next }: { next: string }) {
  const router = useRouter();
  const [fullName, setFullName] = useState('');
  const [msisdn, setMsisdn] = useState('');
  const [district, setDistrict] = useState('');
  const [plan, setPlan] = useState<PlanType>('prepaid');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<React.ReactNode>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await portalApi.signup({
        full_name: fullName.trim(),
        msisdn,
        district: district.trim(),
        plan_type: plan,
        password,
      });
      router.push(next);
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'msisdn_taken' ? (
          <>
            That number already has an account.{' '}
            <AuthLink href={`/signin?next=${encodeURIComponent(next)}`}>Log in</AuthLink> instead.
          </>
        ) : err instanceof ApiError && err.status === 422 ? (
          'Some details don’t look right. Check the number, name and password and try again.'
        ) : (
          'Sign up didn’t go through. Check your connection and try again.'
        )
      );
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border-line bg-surface rounded-panel shadow-panel flex flex-col gap-5 border p-6"
    >
      <Field
        id="signup-name"
        label="Full name"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        autoComplete="name"
        minLength={2}
        maxLength={120}
        autoFocus
        required
      />
      <MsisdnField id="signup-msisdn" value={msisdn} onChange={setMsisdn} />
      <Field
        id="signup-district"
        label="District"
        value={district}
        onChange={(e) => setDistrict(e.target.value)}
        autoComplete="address-level2"
        placeholder="Dhaka"
        minLength={2}
        maxLength={60}
        required
      />

      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm leading-none font-medium">Plan</legend>
        <div className="grid grid-cols-2 gap-3">
          {PLANS.map((p) => (
            <label
              key={p.value}
              className={cn(
                'border-line rounded-button flex cursor-pointer flex-col gap-0.5 border px-4 py-3',
                'has-focus-visible:ring-ring/50 has-focus-visible:ring-[3px]',
                plan === p.value && 'border-primary bg-primary/5'
              )}
            >
              <input
                type="radio"
                name="plan"
                value={p.value}
                checked={plan === p.value}
                onChange={() => setPlan(p.value)}
                className="sr-only"
              />
              <span className="text-sm font-bold">{p.label}</span>
              <span className="text-muted-foreground text-xs">{p.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <Field
        id="signup-password"
        label="Password"
        hint={`At least ${PASSWORD_MIN} characters.`}
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="new-password"
        minLength={PASSWORD_MIN}
        maxLength={PASSWORD_MAX}
        required
      />

      {error && <AuthError id="signup-error">{error}</AuthError>}

      <Button type="submit" size="lg" disabled={submitting}>
        {submitting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
        {submitting ? 'Creating account…' : 'Create account'}
      </Button>

      <p className="text-muted-foreground text-sm">
        Already have an account?{' '}
        <AuthLink href={`/signin?next=${encodeURIComponent(next)}`}>Log in</AuthLink>
      </p>
    </form>
  );
}
