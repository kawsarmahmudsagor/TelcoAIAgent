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
import type { ListingOffer } from '@/lib/types';

// Must match the topic the search_apartments tool sends to in
// backend/app/agent/tools/search_apartments.py.
const APARTMENT_SHORTLIST_TOPIC = 'apartment-shortlist';

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
function useAgentAttribute(key: string): string | undefined {
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

// The tool sends its result the moment the search completes (or earlier, when
// the turn router prefetches it), before the agent has said a word about it. A
// result is held until the agent next *starts* speaking: the reply presenting
// it. Speech already playing when it arrived doesn't count -- a "let me check"
// before the tool ran, or an old reply still playing while a question spoken
// over it is searched. The timer is only a safety net (e.g. a reply that was
// dropped and never spoken).
const FALLBACK_REVEAL_MS = 60_000;

// Must match LISTING_FOCUS_TOPIC in backend/app/agent/listing_focus.py: the one
// listing a reply is about, sent while that reply is generated.
const LISTING_FOCUS_TOPIC = 'listing-focus';

export type PropertyType =
  | 'apartment'
  | 'studio'
  | 'duplex'
  | 'commercial'
  | 'plot';

export interface ApartmentCardData {
  id: string;
  title: string;
  address_line: string;
  city: string;
  neighborhood: string | null;
  price: number;
  listing_type: 'rent' | 'sale';
  property_type: PropertyType;
  bedrooms: number;
  bathrooms: number;
  sqft: number | null;
  amenities: string[];
  image_url: string | null;
  /** Full ordered gallery, cover first. */
  images?: string[] | null;
  /** The listing's live offers (search_apartments adds them). */
  offers?: ListingOffer[];
}

export interface ShortlistResult {
  /** Unique per search result, even when two searches return the same cards. */
  id: number;
  cards: ApartmentCardData[];
  /**
   * Epoch ms when the result was revealed. Used to place it in the transcript
   * after the conversational turn it belongs to, so it keeps its position as
   * the chat moves on instead of trailing the newest message.
   */
  revealedAt: number;
}

export interface UseApartmentShortlistReturn {
  /** Every search result shown this session, oldest first. */
  results: ShortlistResult[];
  /** Dismisses one result (local UI state only). Later searches still show. */
  dismiss: (id: number) => void;
}

/**
 * Search results (several cards) and the single listing a reply is about (one card), in the
 * order they appeared. Each is shown from the moment the agent starts speaking the reply that
 * presents it.
 */
export function useApartmentShortlist(): UseApartmentShortlistReturn {
  const room = useMaybeRoomContext();
  const { state: agentState } = useAgent();
  const [results, setResults] = useState<ShortlistResult[]>([]);
  const nextIdRef = useRef(0);
  // Several searches can land in one turn; each is shown, in order.
  const pendingRef = useRef<ApartmentCardData[][]>([]);
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const agentStateRef = useRef(agentState);
  agentStateRef.current = agentState;

  const show = (batches: ApartmentCardData[][]) => {
    const queued = batches.filter((cards) => cards.length > 0);
    if (queued.length === 0) return;
    const now = Date.now();
    setResults((prev) => [
      ...prev,
      ...queued.map((cards) => ({ id: ++nextIdRef.current, cards, revealedAt: now })),
    ]);
  };

  const revealPending = () => {
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    const due = pendingRef.current;
    pendingRef.current = [];
    show(due);
  };

  const hold = (cards: ApartmentCardData[]) => {
    pendingRef.current.push(cards);
    if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
    fallbackTimerRef.current = setTimeout(revealPending, FALLBACK_REVEAL_MS);
  };

  useEffect(() => {
    if (!room) return;

    const onShortlist = (reader: { readAll: () => Promise<string> }) => {
      reader
        .readAll()
        .then((text) => hold(JSON.parse(text) as ApartmentCardData[]))
        .catch((err) => console.error('Failed to parse apartment shortlist stream:', err));
    };
    // Sent while the reply about it is generated: if that reply is already playing, now.
    const onFocus = (reader: { readAll: () => Promise<string> }) => {
      reader
        .readAll()
        .then((text) => {
          const card = JSON.parse(text) as ApartmentCardData;
          if (agentStateRef.current === 'speaking') show([[card]]);
          else hold([card]);
        })
        .catch((err) => console.error('Failed to parse listing focus stream:', err));
    };

    room.registerTextStreamHandler(APARTMENT_SHORTLIST_TOPIC, onShortlist);
    room.registerTextStreamHandler(LISTING_FOCUS_TOPIC, onFocus);
    return () => {
      room.unregisterTextStreamHandler(APARTMENT_SHORTLIST_TOPIC);
      room.unregisterTextStreamHandler(LISTING_FOCUS_TOPIC);
    };
    // show/hold/revealPending only use refs and the stable setResults.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room]);

  const prevStateRef = useRef(agentState);
  useEffect(() => {
    const prev = prevStateRef.current;
    prevStateRef.current = agentState;
    const startedSpeaking = agentState === 'speaking' && prev !== 'speaking';
    // The reply was dropped: no speaking transition is coming.
    const gaveUp = agentState === 'listening' && prev === 'thinking';
    if ((startedSpeaking || gaveUp) && pendingRef.current.length > 0) revealPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentState]);

  useEffect(
    () => () => {
      if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
    },
    []
  );

  return {
    results,
    dismiss: (id) => setResults((prev) => prev.filter((r) => r.id !== id)),
  };
}

// Must match BOOKING_FORM_TOPIC in backend/app/agent/booking.py.
const BOOKING_FORM_TOPIC = 'booking-form';

export type BookingFormState = 'collecting' | 'review' | 'booking' | 'booked';

/** The viewing booking form as the agent last sent it. */
export interface BookingFormData {
  form_id: string;
  state: BookingFormState;
  /** Bumped by the agent on every change. */
  revision: number;
  full_name: string | null;
  /** Local format, e.g. "01711234567". */
  phone: string | null;
  property_title: string | null;
  /** ISO 8601 with the agency's offset. */
  proposed_datetime: string | null;
  /** Field ("full_name", "phone", "form", ...) -> message. */
  errors: Record<string, string>;
}

export interface BookingFormEntry {
  form: BookingFormData;
  /**
   * Epoch ms when the form first arrived. Like a shortlist's, it pins the card
   * to the turn it appeared in while later updates change it in place.
   */
  revealedAt: number;
  /** Epoch ms of the latest change shown, so the call overlay can bring the form back on top. */
  updatedAt: number;
}

/**
 * The booking forms the agent opened this session, oldest first, each at its
 * latest state. Mount once: livekit-client allows one handler per topic.
 */
export function useBookingForm(): BookingFormEntry[] {
  const room = useMaybeRoomContext();
  const { state: agentState } = useAgent();
  const [forms, setForms] = useState<BookingFormEntry[]>([]);
  // Like a shortlist, a new form waits for the agent's voice (the reply that asks
  // for the name and number) before it appears. Only its first appearance waits:
  // updates to a form on screen apply at once. Latest held state per form_id.
  const heldRef = useRef(new Map<string, BookingFormData>());
  const shownRef = useRef(new Set<string>());
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const agentStateRef = useRef(agentState);
  agentStateRef.current = agentState;

  const upsert = (form: BookingFormData) => {
    shownRef.current.add(form.form_id);
    setForms((prev) => {
      const index = prev.findIndex((entry) => entry.form.form_id === form.form_id);
      const now = Date.now();
      if (index === -1) return [...prev, { form, revealedAt: now, updatedAt: now }];
      // A stream that arrives late must not undo a newer state.
      if (form.revision < prev[index].form.revision) return prev;
      const next = [...prev];
      const changed = form.revision > prev[index].form.revision;
      next[index] = { ...prev[index], form, updatedAt: changed ? now : prev[index].updatedAt };
      return next;
    });
  };

  const revealHeld = () => {
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    const held = [...heldRef.current.values()];
    heldRef.current.clear();
    held.forEach(upsert);
  };

  useEffect(() => {
    if (!room) return;
    const reset = () => {
      heldRef.current.clear();
      shownRef.current.clear();
      if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
      setForms([]);
    };
    const handler = (reader: TextStreamReader) => {
      reader
        .readAll()
        .then((payload) => {
          const form = JSON.parse(payload) as BookingFormData;
          const held = heldRef.current.get(form.form_id);
          if (held) {
            if (form.revision > held.revision) heldRef.current.set(form.form_id, form);
            return;
          }
          if (shownRef.current.has(form.form_id) || agentStateRef.current === 'speaking') {
            // Already on screen, or the agent is mid-reply: no transition to wait for.
            upsert(form);
            return;
          }
          heldRef.current.set(form.form_id, form);
          if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
          fallbackTimerRef.current = setTimeout(revealHeld, FALLBACK_REVEAL_MS);
        })
        .catch((err) => console.error('Failed to read booking form:', err));
    };
    room.registerTextStreamHandler(BOOKING_FORM_TOPIC, handler);
    room.on(RoomEvent.Disconnected, reset);
    return () => {
      room.unregisterTextStreamHandler(BOOKING_FORM_TOPIC);
      room.off(RoomEvent.Disconnected, reset);
      reset();
    };
    // upsert/revealHeld only use refs and the stable setForms.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room]);

  const prevStateRef = useRef(agentState);
  useEffect(() => {
    const startedSpeaking = agentState === 'speaking' && prevStateRef.current !== 'speaking';
    // The reply was dropped: no speaking transition is coming.
    const gaveUp = agentState === 'listening' && prevStateRef.current === 'thinking';
    prevStateRef.current = agentState;
    if ((startedSpeaking || gaveUp) && heldRef.current.size > 0) revealHeld();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentState]);

  return forms;
}
