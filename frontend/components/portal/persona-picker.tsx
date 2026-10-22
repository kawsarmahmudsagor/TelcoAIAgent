'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2Icon, MapPinIcon, RotateCwIcon } from 'lucide-react';
import { ApiError } from '@/lib/api-client';
import { portalApi } from '@/lib/portal-api';
import { cn } from '@/lib/shadcn/utils';
import type { PersonaCard } from '@/lib/types/portal';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; personas: PersonaCard[] };

// Avatar gradients, one per seeded persona in order (the reference's profile avatar is the first).
const AVATAR_GRADIENTS = [
  'from-[#f4b58e] to-[#dd6c8d]',
  'from-[#6158f5] to-[#9b8cff]',
  'from-[#20b89a] to-[#6fd6c0]',
  'from-[#ff9b55] to-[#f6c177]',
  'from-[#e45b73] to-[#b46fe0]',
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (
    (parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')
  ).toUpperCase();
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'The portal could not be reached.';
}

/**
 * The demo's front door: the five seeded subscribers as cards. Picking one signs in as that
 * persona (FastAPI sets the `portal_session` cookie) and opens the portal.
 */
export function PersonaPicker() {
  const router = useRouter();
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [signingIn, setSigningIn] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const fetchPersonas = useCallback(async () => {
    setLoad({ status: 'loading' });
    try {
      setLoad({ status: 'ready', personas: await portalApi.personas() });
    } catch (error) {
      setLoad({ status: 'error', message: errorText(error) });
    }
  }, []);

  useEffect(() => {
    void fetchPersonas();
  }, [fetchPersonas]);

  async function signIn(persona: PersonaCard) {
    setSigningIn(persona.msisdn);
    setLoginError(null);
    try {
      await portalApi.login(persona.msisdn);
      router.push('/portal');
    } catch (error) {
      setLoginError(`Could not sign in as ${persona.full_name}. ${errorText(error)}`);
      setSigningIn(null);
    }
  }

  if (load.status === 'error') {
    return (
      <div
        role="alert"
        className="border-line bg-surface rounded-panel shadow-panel flex flex-col items-start gap-3 border p-6"
      >
        <p className="font-semibold">The demo customers did not load.</p>
        <p className="text-muted-foreground text-sm">{load.message}</p>
        <button
          type="button"
          onClick={() => void fetchPersonas()}
          className="bg-primary text-primary-foreground rounded-button focus-visible:ring-ring inline-flex min-h-11 items-center gap-2 px-4 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
        >
          <RotateCwIcon aria-hidden="true" className="size-4" />
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {loginError && (
        <p
          role="alert"
          className="bg-status-failed text-status-failed-foreground rounded-button px-4 py-3 text-sm font-medium"
        >
          {loginError}
        </p>
      )}
      <ul
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        aria-busy={load.status === 'loading'}
      >
        {load.status === 'loading'
          ? Array.from({ length: 5 }, (_, i) => (
              <li
                key={i}
                aria-hidden="true"
                className="border-line bg-surface rounded-metric h-[188px] animate-pulse border"
              />
            ))
          : load.personas.map((persona, index) => (
              <li key={persona.msisdn}>
                <PersonaButton
                  persona={persona}
                  gradient={AVATAR_GRADIENTS[index % AVATAR_GRADIENTS.length]}
                  pending={signingIn === persona.msisdn}
                  disabled={signingIn !== null}
                  onSelect={() => void signIn(persona)}
                />
              </li>
            ))}
      </ul>
    </div>
  );
}

function PersonaButton({
  persona,
  gradient,
  pending,
  disabled,
  onSelect,
}: {
  persona: PersonaCard;
  gradient: string;
  pending: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  const postpaid = persona.plan_type === 'postpaid';
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      aria-label={`Sign in as ${persona.full_name}, ${persona.plan_type}, ${persona.district}: ${persona.headline}`}
      className={cn(
        'group border-line bg-surface rounded-metric shadow-panel flex h-full w-full flex-col gap-4 border p-[18px] text-left outline-none',
        'focus-visible:border-primary focus-visible:ring-primary/30 focus-visible:ring-4',
        'motion-safe:transition-[border-color,transform] motion-safe:duration-150',
        'enabled:hover:border-[#b7b2ff] enabled:motion-safe:hover:-translate-y-0.5',
        disabled && !pending && 'opacity-55',
        pending && 'border-primary'
      )}
    >
      <span className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className={cn(
            'grid size-11 shrink-0 place-items-center rounded-full bg-linear-135 text-sm font-extrabold text-white',
            gradient
          )}
        >
          {initials(persona.full_name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-bold tracking-[-0.01em]">
            {persona.full_name}
          </span>
          <span className="text-muted-foreground block text-xs tabular-nums">
            {persona.masked_msisdn}
          </span>
        </span>
        <span
          className={cn(
            'rounded-md px-2 py-1 text-[11px] font-bold capitalize',
            postpaid ? 'bg-tint-green text-success' : 'bg-status-open text-status-open-foreground'
          )}
        >
          {persona.plan_type}
        </span>
      </span>

      <span className="bg-surface2 rounded-button flex-1 px-3 py-2.5 text-[13px] leading-snug font-semibold">
        {persona.headline}
      </span>

      <span className="text-muted-foreground flex items-center justify-between gap-2 text-xs">
        <span className="inline-flex items-center gap-1.5">
          <MapPinIcon aria-hidden="true" className="size-3.5" />
          {persona.district}
        </span>
        <span className="text-primary inline-flex items-center gap-1.5 font-semibold">
          {pending ? (
            <>
              <Loader2Icon aria-hidden="true" className="size-3.5 animate-spin" />
              Signing in…
            </>
          ) : (
            'Sign in'
          )}
        </span>
      </span>
    </button>
  );
}
