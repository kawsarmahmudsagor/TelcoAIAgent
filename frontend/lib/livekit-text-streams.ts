'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ConnectionState,
  ParticipantEvent,
  RoomEvent,
  type TextStreamReader,
} from 'livekit-client';
import {
  type ReceivedMessage,
  useAgent,
  useMaybeRoomContext,
  useVoiceAssistant,
} from '@livekit/components-react';

// Must match USER_TURN_TOPIC / GATE_ATTRIBUTE in backend/app/agent/gated_agent.py.
const USER_TURN_TOPIC = 'user-turn';
const GATE_ATTRIBUTE = 'turn_gate';
// Must match IGNORED_TEXT_TOPIC in backend/app/agent/gated_agent.py.
const IGNORED_TEXT_TOPIC = 'ignored-text';

// Must match GREETING_DONE_ATTRIBUTE in backend/app/agent/entrypoint.py.
const GREETING_DONE_ATTRIBUTE = 'greeting_done';
// If the attribute never arrives (an older agent, a lost update), Send is
// enabled anyway this long after connecting.
const GREETING_FALLBACK_MS = 30_000;

type UserTurnMessage = Extract<ReceivedMessage, { type: 'userTranscript' }>;

/**
 * One of the agent participant's attributes. Read from the participant itself:
 * useAgent().attributes (components-react 2.9) holds only the keys of the
 * latest change event, so the agent's next state update would wipe it.
 */
export function useAgentAttribute(key: string): string | undefined {
  const { agent } = useVoiceAssistant();
  const [value, setValue] = useState<string | undefined>(() => agent?.attributes[key]);

  useEffect(() => {
    if (!agent) {
      setValue(undefined);
      return;
    }
    const update = () => setValue(agent.attributes[key]);
    update();
    agent.on(ParticipantEvent.AttributesChanged, update);
    return () => {
      agent.off(ParticipantEvent.AttributesChanged, update);
    };
  }, [agent, key]);

  return value;
}

/**
 * The voice turns the agent took, as transcript messages. The agent publishes
 * each one it answers on USER_TURN_TOPIC; speech it ignored (the turn gate's
 * drops, or speech it couldn't answer, e.g. during the greeting) never arrives.
 */
function useAcceptedUserTurns(): UserTurnMessage[] {
  const room = useMaybeRoomContext();
  const [turns, setTurns] = useState<UserTurnMessage[]>([]);

  useEffect(() => {
    if (!room) return;
    const reset = () => setTurns([]);
    const handler = (reader: TextStreamReader) => {
      const { id, timestamp } = reader.info;
      reader
        .readAll()
        .then((payload) => {
          const { text } = JSON.parse(payload) as { text: string };
          setTurns((prev) => [
            ...prev,
            { type: 'userTranscript', id, timestamp, message: text, from: room.localParticipant },
          ]);
        })
        .catch((err) => console.error('Failed to read accepted user turn:', err));
    };
    room.registerTextStreamHandler(USER_TURN_TOPIC, handler);
    room.on(RoomEvent.Disconnected, reset);
    return () => {
      room.unregisterTextStreamHandler(USER_TURN_TOPIC);
      room.off(RoomEvent.Disconnected, reset);
      reset();
    };
  }, [room]);

  return turns;
}

/**
 * Ids of typed messages the agent ignored (off-topic requests, in gated
 * sessions) -- the id is the text stream id the message was sent with.
 */
function useIgnoredTextIds(): ReadonlySet<string> {
  const room = useMaybeRoomContext();
  const [ids, setIds] = useState<ReadonlySet<string>>(() => new Set());

  useEffect(() => {
    if (!room) return;
    const reset = () => setIds(new Set());
    const handler = (reader: TextStreamReader) => {
      reader
        .readAll()
        .then((payload) => {
          const { id } = JSON.parse(payload) as { id: string };
          setIds((prev) => new Set(prev).add(id));
        })
        .catch((err) => console.error('Failed to read ignored text message:', err));
    };
    room.registerTextStreamHandler(IGNORED_TEXT_TOPIC, handler);
    room.on(RoomEvent.Disconnected, reset);
    return () => {
      room.unregisterTextStreamHandler(IGNORED_TEXT_TOPIC);
      room.off(RoomEvent.Disconnected, reset);
      reset();
    };
  }, [room]);

  return ids;
}

/**
 * Puts accepted voice turns in place of the raw user transcription. Each turn
 * goes before the first agent message stamped after it -- both timestamps come
 * from the agent, so no browser/server clock skew.
 */
export function mergeAcceptedTurns(
  messages: ReceivedMessage[],
  turns: UserTurnMessage[]
): ReceivedMessage[] {
  const pending = [...turns].sort((a, b) => a.timestamp - b.timestamp);
  const out: ReceivedMessage[] = [];
  for (const message of messages) {
    if (message.type === 'userTranscript') continue;
    if (message.type === 'agentTranscript') {
      while (pending.length > 0 && pending[0].timestamp <= message.timestamp) {
        out.push(pending.shift()!);
      }
    }
    out.push(message);
  }
  return [...out, ...pending];
}

/**
 * The transcript to show. When the agent publishes the voice turns it takes
 * (it sets the turn_gate attribute -- every browser session does, gated or
 * not), only those are shown in place of the raw transcription; typed chat
 * messages stay unless the agent reports it ignored one (off-topic). An older
 * agent that doesn't set it gets the messages unchanged.
 */
export function useVisibleMessages(messages: ReceivedMessage[]): ReceivedMessage[] {
  const gated = useAgentAttribute(GATE_ATTRIBUTE) === '1';
  const turns = useAcceptedUserTurns();
  const ignored = useIgnoredTextIds();
  return useMemo(() => {
    const shown = ignored.size > 0 ? messages.filter((m) => !ignored.has(m.id)) : messages;
    return gated ? mergeAcceptedTurns(shown, turns) : shown;
  }, [gated, messages, turns, ignored]);
}

/**
 * Whether the agent's first message (the greeting) has finished. The agent
 * takes no input until then -- typed text sent earlier is dropped -- and sets
 * the greeting_done attribute when it's over. Fallbacks, should that never
 * arrive: the agent's first speaking -> listening transition, or
 * GREETING_FALLBACK_MS after connecting. Resets when the room disconnects.
 */
export function useGreetingDone(): boolean {
  const room = useMaybeRoomContext();
  const { state: agentState } = useAgent();
  const flagged = useAgentAttribute(GREETING_DONE_ATTRIBUTE) === '1';
  const [fallbackDone, setFallbackDone] = useState(false);
  const spokeRef = useRef(false);

  useEffect(() => {
    if (!room) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const start = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setFallbackDone(true), GREETING_FALLBACK_MS);
    };
    const reset = () => {
      clearTimeout(timer);
      spokeRef.current = false;
      setFallbackDone(false);
    };
    if (room.state === ConnectionState.Connected) start();
    room.on(RoomEvent.Connected, start);
    room.on(RoomEvent.Disconnected, reset);
    return () => {
      clearTimeout(timer);
      room.off(RoomEvent.Connected, start);
      room.off(RoomEvent.Disconnected, reset);
    };
  }, [room]);

  useEffect(() => {
    if (agentState === 'speaking') {
      spokeRef.current = true;
    } else if (agentState === 'listening' && spokeRef.current) {
      setFallbackDone(true);
    }
  }, [agentState]);

  return flagged || fallbackDone;
}
