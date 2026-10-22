'use client';

import { motion, useReducedMotion } from 'motion/react';
import { type AgentState, type TrackReference, useTrackVolume } from '@livekit/components-react';
import { cn } from '@/lib/shadcn/utils';

/** Who the call screen is animating for: the agent's voice, the caller's, or nobody. */
export type CallActivity = 'agent' | 'user' | null;

// Resting scale of each ripple ring, relative to the avatar.
const RING_STEPS = [1.14, 1.3, 1.46];

/**
 * Brass ripples around the avatar while the agent talks, sized by its voice. With the speaker
 * off there is no audio to measure, so they pulse on the agent state instead. Volume is read
 * here, in a leaf, so the per-frame updates don't re-render the rest of the call screen.
 */
function AgentRings({
  track,
  active,
  muted,
}: {
  track?: TrackReference;
  active: boolean;
  muted: boolean;
}) {
  const reduceMotion = useReducedMotion();
  const volume = useTrackVolume(active && !muted ? track : undefined);
  const level = Math.min(1, volume * 3);

  return RING_STEPS.map((step, i) => {
    const restOpacity = 0.14 - i * 0.04;
    let animate: { scale: number | number[]; opacity: number | number[] };
    let transition: object = { duration: 0.14, ease: 'easeOut' };

    if (!active) {
      animate = { scale: step, opacity: restOpacity };
      transition = { duration: 0.6, ease: 'easeOut' };
    } else if (muted) {
      animate = reduceMotion
        ? { scale: step, opacity: [restOpacity, 0.5 - i * 0.12, restOpacity] }
        : {
            scale: [step, step + 0.08, step],
            opacity: [restOpacity, 0.5 - i * 0.12, restOpacity],
          };
      transition = { duration: 1.4, repeat: Infinity, ease: 'easeInOut', delay: i * 0.18 };
    } else {
      animate = {
        scale: reduceMotion ? step : step + level * 0.06 * (i + 1),
        opacity: restOpacity + level * (0.42 - i * 0.12),
      };
    }

    return (
      <motion.span
        key={step}
        aria-hidden="true"
        initial={false}
        animate={animate}
        transition={transition}
        className="border-brass absolute inset-0 rounded-full border-2"
      />
    );
  });
}

/** An evergreen halo that swells with the caller's voice. */
function UserRing({ track, active }: { track?: TrackReference; active: boolean }) {
  const reduceMotion = useReducedMotion();
  const volume = useTrackVolume(active ? track : undefined);
  const level = active ? Math.min(1, volume * 4) : 0;

  return (
    <motion.span
      aria-hidden="true"
      initial={false}
      animate={{
        opacity: active ? 0.45 + level * 0.55 : 0,
        scale: reduceMotion ? 1.06 : 1.04 + level * 0.08,
      }}
      transition={{ duration: active ? 0.12 : 0.4, ease: 'easeOut' }}
      className="border-primary absolute inset-0 rounded-full border-[3px] shadow-[0_0_32px_-4px_var(--primary)]"
    />
  );
}

interface CallAvatarProps {
  activity: CallActivity;
  agentState: AgentState;
  agentTrack?: TrackReference;
  micTrack?: TrackReference;
  speakerMuted: boolean;
  className?: string;
}

export function CallAvatar({
  activity,
  agentState,
  agentTrack,
  micTrack,
  speakerMuted,
  className,
}: CallAvatarProps) {
  return (
    <div className={cn('relative aspect-square', className)}>
      <AgentRings track={agentTrack} active={activity === 'agent'} muted={speakerMuted} />
      <UserRing track={micTrack} active={activity === 'user'} />

      {/* Thinking: a slow brass arc around the portrait. */}
      <svg
        aria-hidden="true"
        viewBox="0 0 100 100"
        className={cn(
          'text-brass absolute -inset-[5%] size-[110%] transition-opacity duration-300',
          'animate-spin [animation-duration:2.4s] motion-reduce:animate-none',
          agentState === 'thinking' ? 'opacity-100' : 'opacity-0'
        )}
      >
        <circle
          cx="50"
          cy="50"
          r="48"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeDasharray="70 232"
        />
      </svg>

      <div className="bg-card ring-brass/50 ring-offset-background relative size-full overflow-hidden rounded-full ring-2 ring-offset-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/agent-avatar.svg"
          alt="Your agent"
          draggable={false}
          className="size-full object-cover select-none"
        />
      </div>
    </div>
  );
}
