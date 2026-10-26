import { useEffect, useRef, useState } from 'react';
import { useSessionContext, useVoiceAssistant } from '@livekit/components-react';

// Must match END_CALL_RPC in backend/app/agent/browser_end_call.py.
const END_CALL_RPC = 'end_call';
// After the agent stops speaking, so the goodbye's last audio has played here too.
const AFTER_SPEECH_MS = 600;
// Calls onEnd even if the agent still shows as speaking (a stuck state).
const MAX_WAIT_MS = 15_000;

/**
 * Runs `onEnd` when the agent asks to, after its goodbye: the agent calls the `end_call` RPC
 * once the goodbye has played on its side, and this waits until the agent is no longer
 * speaking here. In the portal `onEnd` turns the mic off; the session stays connected.
 */
export function useAgentEndCall(onEnd: () => void) {
  const { room } = useSessionContext();
  const { state: agentState } = useVoiceAssistant();
  const [requested, setRequested] = useState(false);
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;
  const endRef = useRef(() => {
    setRequested(false);
    onEndRef.current();
  });

  useEffect(() => {
    room.registerRpcMethod(END_CALL_RPC, async () => {
      setRequested(true);
      return '';
    });
    return () => {
      room.unregisterRpcMethod(END_CALL_RPC);
      setRequested(false);
    };
  }, [room]);

  useEffect(() => {
    if (!requested) return;
    const timer = setTimeout(endRef.current, MAX_WAIT_MS);
    return () => clearTimeout(timer);
  }, [requested]);

  useEffect(() => {
    if (!requested || agentState === 'speaking') return;
    const timer = setTimeout(endRef.current, AFTER_SPEECH_MS);
    return () => clearTimeout(timer);
  }, [requested, agentState]);
}
