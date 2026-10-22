import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { useSessionContext } from '@livekit/components-react';

/**
 * Turns the microphone on each time the session connects. Sessions start with the mic off
 * because enabling it inside `start()` makes a denied permission reject the whole connect;
 * here a denial only shows a toast and text chat keeps working.
 */
export function useMicOnConnect() {
  const { isConnected, room } = useSessionContext();
  const wasConnectedRef = useRef(false);

  useEffect(() => {
    const wasConnected = wasConnectedRef.current;
    wasConnectedRef.current = isConnected;
    if (!isConnected || wasConnected) return;

    // No automatic gain control: it turns a quiet room up while the customer listens, and
    // the agent tells the customer from people around them by how loud they are
    // (backend app/agent/voice_level.py). Kept in the room defaults so a re-created mic
    // track (device switch) stays the same.
    room.options.audioCaptureDefaults = {
      ...room.options.audioCaptureDefaults,
      autoGainControl: false,
    };
    room.localParticipant
      .setMicrophoneEnabled(true, { autoGainControl: false })
      .catch((error: unknown) => {
        console.warn('Could not turn on the microphone:', error);
        toast.warning('Microphone is off', {
          description:
            'We couldn’t use your microphone. You can keep chatting by text, or allow it and turn the mic on.',
        });
      });
  }, [isConnected, room]);
}
