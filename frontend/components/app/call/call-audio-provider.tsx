'use client';

import { createContext, useContext, useMemo, useState } from 'react';
import type { UseSessionReturn } from '@livekit/components-react';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';

interface CallAudioContextValue {
  /** The agent's voice is switched off (the speaker button). */
  muted: boolean;
  toggleMuted: () => void;
}

const CallAudioContext = createContext<CallAudioContextValue | null>(null);

/**
 * AgentSessionProvider plus the call screen's speaker switch. Muting goes through the audio
 * renderer's `muted` prop, which unsubscribes the agent's audio: the agent's track volume reads 0
 * while muted. Each call starts unmuted.
 */
export function CallAudioProvider({
  session,
  children,
}: {
  session: UseSessionReturn;
  children: React.ReactNode;
}) {
  const [muted, setMuted] = useState(false);
  const [wasConnected, setWasConnected] = useState(session.isConnected);
  if (wasConnected !== session.isConnected) {
    setWasConnected(session.isConnected);
    if (!session.isConnected) setMuted(false);
  }

  const value = useMemo(() => ({ muted, toggleMuted: () => setMuted((m) => !m) }), [muted]);

  return (
    <CallAudioContext.Provider value={value}>
      <AgentSessionProvider session={session} muted={muted}>
        {children}
      </AgentSessionProvider>
    </CallAudioContext.Provider>
  );
}

const NOT_PROVIDED: CallAudioContextValue = { muted: false, toggleMuted: () => {} };

export function useCallAudio(): CallAudioContextValue {
  return useContext(CallAudioContext) ?? NOT_PROVIDED;
}
