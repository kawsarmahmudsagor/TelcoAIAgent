import { useEffect, useRef } from 'react';
import type { Room } from 'livekit-client';
import { toast } from 'sonner';
import { useSessionContext } from '@livekit/components-react';

/**
 * Turns the microphone on; a denial only shows a toast. Resolves true when the mic is on.
 */
export async function turnOnMicrophone(room: Room): Promise<boolean> {
  // No automatic gain control: it turns a quiet room up while the customer listens, and
  // the agent tells the customer from people around them by how loud they are
  // (backend app/agent/voice_level.py). Kept in the room defaults so a re-created mic
  // track (device switch) stays the same.
  room.options.audioCaptureDefaults = {
    ...room.options.audioCaptureDefaults,
    autoGainControl: false,
  };
  try {
    await room.localParticipant.setMicrophoneEnabled(true, { autoGainControl: false });
    return true;
  } catch (error: unknown) {
    console.warn('Could not turn on the microphone:', error);
    toast.warning('Microphone is off', {
      description:
        'We couldn’t use your microphone. You can keep chatting by text, or allow it and turn the mic on.',
    });
    return false;
  }
}

/**
 * Turns the microphone on each time the session connects. Sessions start with the mic off
 * because enabling it inside `start()` makes a denied permission reject the whole connect;
 * here a denial only shows a toast and text chat keeps working. With `enabled` false at the
 * moment of connecting (a text-only session), the mic stays off.
 */
export function useMicOnConnect(enabled = true) {
  const { isConnected, room } = useSessionContext();
  const wasConnectedRef = useRef(false);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  useEffect(() => {
    const wasConnected = wasConnectedRef.current;
    wasConnectedRef.current = isConnected;
    if (!isConnected || wasConnected || !enabledRef.current) return;

    void turnOnMicrophone(room);
  }, [isConnected, room]);
}
