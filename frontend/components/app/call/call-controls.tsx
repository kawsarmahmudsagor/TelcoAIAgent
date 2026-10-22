'use client';

import { MicIcon, MicOffIcon, PhoneOffIcon, Volume2Icon, VolumeXIcon } from 'lucide-react';
import { useInputControls } from '@/hooks/agents-ui/use-agent-control-bar';
import { cn } from '@/lib/shadcn/utils';
import { useCallAudio } from './call-audio-provider';

const ROUND =
  'grid shrink-0 place-items-center rounded-full outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/60 disabled:opacity-50';
const QUIET =
  'size-12 @5xl:size-14 border border-white/10 bg-white/[0.06] text-foreground backdrop-blur-md hover:bg-white/[0.12]';
// A switched-off mic or speaker reads as "on" visually: a filled light button.
const QUIET_OFF = 'border-transparent bg-foreground text-background hover:bg-foreground/85';

interface CallControlsProps {
  onEndCall: () => void;
  className?: string;
}

/** Mic, End call and Speaker: the call's three buttons. */
export function CallControls({ onEndCall, className }: CallControlsProps) {
  const { microphoneToggle } = useInputControls();
  const { muted: speakerMuted, toggleMuted } = useCallAudio();
  const micOff = !microphoneToggle.enabled;

  return (
    <div className={cn('flex items-center gap-3 @5xl:gap-8', className)}>
      <button
        type="button"
        onClick={() => void microphoneToggle.toggle()}
        disabled={microphoneToggle.pending}
        aria-label="Mute microphone"
        aria-pressed={micOff}
        title={micOff ? 'Unmute microphone' : 'Mute microphone'}
        className={cn(ROUND, QUIET, micOff && QUIET_OFF)}
      >
        {micOff ? (
          <MicOffIcon aria-hidden="true" className="size-6" />
        ) : (
          <MicIcon aria-hidden="true" className="size-6" />
        )}
      </button>

      <button
        type="button"
        onClick={onEndCall}
        aria-label="End call"
        title="End call"
        className={cn(
          ROUND,
          'bg-destructive size-14 text-white shadow-[0_8px_28px_-6px_var(--destructive)] hover:brightness-110 @5xl:size-16'
        )}
      >
        <PhoneOffIcon aria-hidden="true" className="size-7" />
      </button>

      <button
        type="button"
        onClick={toggleMuted}
        aria-label="Mute speaker"
        aria-pressed={speakerMuted}
        title={speakerMuted ? 'Turn speaker on' : 'Turn speaker off'}
        className={cn(ROUND, QUIET, speakerMuted && QUIET_OFF)}
      >
        {speakerMuted ? (
          <VolumeXIcon aria-hidden="true" className="size-6" />
        ) : (
          <Volume2Icon aria-hidden="true" className="size-6" />
        )}
      </button>
    </div>
  );
}
