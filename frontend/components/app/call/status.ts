import type { AgentState } from '@livekit/components-react';

/** What the call screen says under the agent's name. */
export function statusLabel(state: AgentState): string {
  switch (state) {
    case 'speaking':
      return 'Speaking…';
    case 'thinking':
      return 'Thinking…';
    case 'listening':
      return 'Listening…';
    case 'failed':
    case 'disconnected':
      return 'Call ended';
    case 'connecting':
    case 'initializing':
    case 'idle':
    case 'pre-connect-buffering':
    default:
      return 'Connecting…';
  }
}
