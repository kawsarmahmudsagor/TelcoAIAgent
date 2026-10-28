'use client';

import { useAgentAttribute } from '@/lib/livekit-text-streams';

/**
 * How the assistant session uses voice: `off` (type and read, when the agent could not apply
 * a mode), `text_reply` (the visitor may speak; replies are text) or `full` (voice both ways).
 */
export type VoiceMode = 'off' | 'text_reply' | 'full';

// Must match VOICE_ATTRIBUTE in backend/app/agent/voice_mode.py.
export const VOICE_ATTRIBUTE = 'voice';

const MODES: readonly string[] = ['off', 'text_reply', 'full'] satisfies VoiceMode[];

/**
 * The agent's published voice mode. Before the agent has published one (no session yet, or still
 * joining) anyone, guest or signed in, may speak. The agent enforces the mode either way; this
 * only drives what the UI offers.
 */
export function useVoiceMode(): VoiceMode {
  const published = useAgentAttribute(VOICE_ATTRIBUTE);
  if (published !== undefined && MODES.includes(published)) return published as VoiceMode;
  return 'full';
}
