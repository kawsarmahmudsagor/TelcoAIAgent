'use client';

import type { AgentState, TrackReference } from '@livekit/components-react';
import { AgentAudioVisualizerBar } from '@/components/agents-ui/agent-audio-visualizer-bar';
import { cn } from '@/lib/shadcn/utils';
import type { CallActivity } from './call-avatar';

interface CallWaveformProps {
  activity: CallActivity;
  agentState: AgentState;
  agentTrack?: TrackReference;
  micTrack?: TrackReference;
  speakerMuted: boolean;
  className?: string;
}

/**
 * The voice line under the agent's name: brass for the agent, evergreen for the caller. The bar
 * visualizer only follows audio in the `speaking` state, so the caller's mic is shown as
 * "speaking" too. With the speaker off there is no agent audio to follow, so it runs the
 * `thinking` sequence instead of lying flat.
 */
export function CallWaveform({
  activity,
  agentState,
  agentTrack,
  micTrack,
  speakerMuted,
  className,
}: CallWaveformProps) {
  let state: AgentState = agentState;
  let track: TrackReference | undefined;
  let tone = 'text-foreground/45';

  if (activity === 'agent') {
    tone = 'text-brass';
    if (speakerMuted) state = 'thinking';
    else track = agentTrack;
  } else if (activity === 'user') {
    tone = 'text-primary';
    state = 'speaking';
    track = micTrack;
  } else if (agentState === 'thinking') {
    tone = 'text-brass/80';
  }

  return (
    <AgentAudioVisualizerBar
      aria-hidden="true"
      size="icon"
      barCount={23}
      state={state}
      audioTrack={track}
      className={cn('h-12 gap-[5px] transition-colors duration-300', tone, className)}
    >
      <div className="min-h-[5px] w-[3px] rounded-full bg-current/25 transition-[background-color,height] duration-150 ease-out data-[lk-highlighted=true]:bg-current" />
    </AgentAudioVisualizerBar>
  );
}
