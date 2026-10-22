'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { PhoneIcon, PhoneOffIcon } from 'lucide-react';
import { motion } from 'motion/react';
import { useRingtone } from '@/hooks/useRingtone';
import { type CallDeclineReason, type Client, type IncomingCall, api } from '@/lib/api-client';

const RING_TIMEOUT_MS = 60_000;
const STATUS_POLL_MS = 3000;
const RINGING_STATUSES = new Set(['dispatched', 'in_progress']);
const SCHEDULE_PATH = '/dashboard/schedule';

/** in_progress only means the room exists -- it stops ringing once someone joins. */
function isRinging(call: IncomingCall): boolean {
  return RINGING_STATUSES.has(call.status) && !call.answered_at;
}

type Phase = 'loading' | 'ringing' | 'unavailable' | 'ending';

/** e.g. "Re: buying a 3-bed apartment in Gulshan" */
function describeTopic(client: Client): string {
  const intent =
    client.rent_or_buy === 'rent' ? 'renting' : client.rent_or_buy === 'buy' ? 'buying' : null;
  const beds = client.bedrooms_wanted ? `${client.bedrooms_wanted}-bed` : null;
  const place = [beds, client.preferred_property_type].filter(Boolean).join(' ');
  if (!intent && !place && !client.preferred_location) {
    return 'Follow-up on your real estate inquiry';
  }
  const what = place ? `a ${place}` : 'a property';
  const where = client.preferred_location ? ` in ${client.preferred_location}` : '';
  return `Re: ${intent ?? 'finding'} ${what}${where}`;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join('');
}

/**
 * Incoming-call screen for a scheduled cold call that just went live (the
 * ScheduledCallWatcher redirects here). Rings until the user answers (joins
 * the existing conversation UI for the call's room), declines (call becomes
 * cancelled), or lets it ring out (call becomes missed).
 */
export default function IncomingCallPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [call, setCall] = useState<IncomingCall | null>(null);
  const [phase, setPhase] = useState<Phase>('loading');
  // Guards against a double action, e.g. Decline clicked as the timeout fires.
  const settledRef = useRef(false);
  const stopRingtone = useRingtone(phase === 'ringing');

  useEffect(() => {
    api
      .incomingCall(id)
      .then((incoming) => {
        setCall(incoming);
        setPhase(isRinging(incoming) ? 'ringing' : 'unavailable');
      })
      .catch(() => setPhase('unavailable'));
  }, [id]);

  const endCall = useCallback(
    async (reason: CallDeclineReason) => {
      if (settledRef.current) return;
      settledRef.current = true;
      stopRingtone();
      setPhase('ending');
      // A 409 just means the call already ended some other way -- either way
      // the schedule page shows its real status.
      await api.declineCall(id, reason).catch(() => {});
      router.replace(SCHEDULE_PATH);
    },
    [id, router, stopRingtone]
  );

  function accept() {
    if (settledRef.current || !call) return;
    settledRef.current = true;
    stopRingtone();
    setPhase('ending');
    const roomName = call.livekit_room_name ?? `coldcall-${call.id}`;
    router.push(`/chat?room=${encodeURIComponent(roomName)}`);
  }

  useEffect(() => {
    if (phase !== 'ringing') return;
    const timeout = setTimeout(() => endCall('missed'), RING_TIMEOUT_MS);
    return () => clearTimeout(timeout);
  }, [phase, endCall]);

  // Stop ringing on our own if the call is answered (e.g. in another dashboard
  // tab) or ends some other way -- otherwise this screen's ring timeout would
  // later try to mark a live call missed.
  useEffect(() => {
    if (phase !== 'ringing') return;
    const interval = setInterval(() => {
      api
        .incomingCall(id)
        .then((latest) => {
          if (settledRef.current || isRinging(latest)) return;
          settledRef.current = true;
          stopRingtone();
          setCall(latest);
          setPhase('unavailable');
        })
        .catch(() => {}); // transient error, next poll will retry
    }, STATUS_POLL_MS);
    return () => clearInterval(interval);
  }, [phase, id, stopRingtone]);

  return (
    <div className="bg-background fixed inset-0 z-50 flex items-center justify-center px-4">
      {phase === 'loading' && <p className="text-muted-foreground text-sm">Connecting…</p>}

      {phase === 'unavailable' && (
        <div className="flex flex-col items-center gap-3 text-center">
          <p className="text-sm">
            {call?.answered_at
              ? 'This call was answered elsewhere.'
              : 'This call is no longer available.'}
          </p>
          <Link href={SCHEDULE_PATH} className="text-primary text-sm underline">
            Back to call schedule
          </Link>
        </div>
      )}

      {(phase === 'ringing' || phase === 'ending') && call && (
        <div className="flex w-full max-w-sm flex-col items-center gap-10 text-center">
          <p className="text-muted-foreground font-mono text-xs tracking-widest uppercase">
            {phase === 'ringing' ? 'Incoming call…' : 'Connecting…'}
          </p>

          <div className="relative flex size-36 items-center justify-center">
            {phase === 'ringing' &&
              [0, 1].map((ring) => (
                <motion.span
                  key={ring}
                  className="absolute inset-0 rounded-full bg-green-500/30"
                  initial={{ scale: 1, opacity: 0.6 }}
                  animate={{ scale: 1.7, opacity: 0 }}
                  transition={{ duration: 2, repeat: Infinity, delay: ring, ease: 'easeOut' }}
                />
              ))}
            <div className="bg-muted relative flex size-28 items-center justify-center rounded-full text-3xl font-semibold">
              {initials(call.agent_display_name)}
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold">{call.agent_display_name}</h1>
            <p className="text-muted-foreground text-sm">{call.operator_name}</p>
            <p className="mt-3 text-sm">{describeTopic(call.client)}</p>
            <p className="text-muted-foreground text-xs">Calling {call.client.full_name}</p>
          </div>

          <div className="flex w-full justify-around">
            <div className="flex flex-col items-center gap-2">
              <button
                type="button"
                onClick={() => endCall('cancelled')}
                disabled={phase !== 'ringing'}
                aria-label="Decline call"
                className="flex size-16 items-center justify-center rounded-full bg-red-600 text-white shadow-lg transition hover:bg-red-700 disabled:opacity-50"
              >
                <PhoneOffIcon className="size-7" />
              </button>
              <span className="text-muted-foreground text-xs">Decline</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <button
                type="button"
                onClick={accept}
                disabled={phase !== 'ringing'}
                aria-label="Accept call"
                className="flex size-16 items-center justify-center rounded-full bg-green-600 text-white shadow-lg transition hover:bg-green-700 disabled:opacity-50"
              >
                <PhoneIcon className="size-7" />
              </button>
              <span className="text-muted-foreground text-xs">Accept</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
