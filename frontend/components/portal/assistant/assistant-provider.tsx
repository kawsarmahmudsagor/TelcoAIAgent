'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ConnectionState, type Room, RoomEvent } from 'livekit-client';
import { toast } from 'sonner';
import {
  type AgentState,
  type ReceivedMessage,
  useChat,
  useLocalParticipant,
  useSessionContext,
  useSessionMessages,
  useVoiceAssistant,
} from '@livekit/components-react';
import { APP_CONFIG_DEFAULTS } from '@/app-config';
import { CallAudioProvider } from '@/components/app/call/call-audio-provider';
import {
  ChatBubbleProvider,
  useChatBubble,
  useOptionalChatBubble,
} from '@/components/chat-bubble/chat-bubble-context';
import { type VoiceMode, useVoiceMode } from '@/components/customer/use-voice-mode';
import { useOptionalPortalMe } from '@/components/portal/portal-me-context';
import { useAgentEndCall } from '@/hooks/useAgentEndCall';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { turnOnMicrophone, useMicOnConnect } from '@/hooks/useMicOnConnect';
import { useAgentAttribute, useGreetingDone, useVisibleMessages } from '@/lib/livekit-text-streams';
import { getVisitorConversation, toReceivedMessages } from '@/lib/public-conversations';
import type { ReplyLanguage } from '@/lib/reply-language';
import { type ConfirmState, type TelcoCard, useTelcoTopics } from '@/lib/telco-topics';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

// Must match CONVERSATION_ATTRIBUTE in backend/app/agent/entrypoint.py: the session's
// conversation row id.
const CONVERSATION_ATTRIBUTE = 'conversation_id';
// Must match ACCOUNT_ATTRIBUTE in backend/app/agent/account_link.py: the session's subscriber
// id, "" for a guest.
const ACCOUNT_ATTRIBUTE = 'account';

/**
 * An agent attribute that outlives the agent leaving the room, for reading once the session has
 * ended. Cleared when the next session connects.
 */
function useLastAgentAttribute(room: Room, key: string) {
  const value = useAgentAttribute(key);
  const ref = useRef<string | null>(null);
  if (value !== undefined) ref.current = value;
  useEffect(() => {
    const clear = () => {
      ref.current = null;
    };
    room.on(RoomEvent.Connected, clear);
    return () => {
      room.off(RoomEvent.Connected, clear);
    };
  }, [room]);
  return ref;
}

export interface AssistantContextValue {
  /**
   * The conversation so far (accepted voice turns, typed messages, the agent's replies), after
   * the stored messages of an earlier chat being carried on.
   */
  messages: ReceivedMessage[];
  /** The chat history list is showing in place of the transcript. */
  historyOpen: boolean;
  setHistoryOpen(open: boolean): void;
  /** The earlier chat being carried on (its id), if any. */
  resumedId: string | null;
  /**
   * The ended conversation on screen, for export: the chat carried on, else the guest session
   * that ended last (with several ended guest sessions on screen, only the last one). Null while
   * a session is up or on its way.
   */
  exportableId: string | null;
  /**
   * Loads an earlier chat from the history and carries it on: a live session is ended first,
   * and the next one reopens that conversation. Resolves false when it couldn't be loaded.
   */
  openConversation(id: string): Promise<boolean>;
  /** Ends any live session and clears the panel for a new conversation. */
  newChat(): void;
  /**
   * A guest just logged in: like newChat, but the language pick stays, and a session that was up
   * starts again as the customer's (voice when the mic was on), so it opens with their greeting.
   */
  startOverForLogin(): void;
  /** Package and case cards, oldest first. */
  cards: TelcoCard[];
  /** The agent's latest confirm card. */
  confirm: ConfirmState | null;
  agentState: AgentState;
  isConnected: boolean;
  /** A session is on its way up (started, not yet connected). */
  connecting: boolean;
  /** The agent has finished its greeting and takes input. */
  ready: boolean;
  /** Typed text waiting for the agent to be ready (shown greyed out in the transcript). */
  queued: string[];
  /**
   * Sends a chat message. With no session it starts a text-only one first, where the agent skips
   * its greeting; until the agent takes input, the text waits in `queued`.
   */
  sendText(text: string): void;
  micEnabled: boolean;
  /** Mic on/off; with no session it starts a voice one. Does nothing when voiceMode is `off`. */
  toggleMic(): void;
  /** Whether this session may use the mic (`off`: a guest, text only) and hears replies. */
  voiceMode: VoiceMode;
  /** Ends the session. */
  end(): void;
  /** The language the customer picked for this chat, or null before the pick. */
  replyLanguage: ReplyLanguage | null;
  chooseReplyLanguage(language: ReplyLanguage): void;
  /** A start (a send, the mic, a call, a notification) is waiting for the pick. */
  languagePending: boolean;
}

const AssistantContext = createContext<AssistantContextValue | null>(null);

/**
 * The portal's one AI assistant session: ChatBubbleProvider's LiveKit session plus everything
 * that must run exactly once per room -- the audio renderer, the transcript and telco topic
 * handlers, the agent's hang-up RPC. Mounted by the portal layout around the whole shell, so the
 * bubble and /portal/assistant show the same conversation and a call survives navigation.
 */
export function AssistantProvider({ children }: { children: React.ReactNode }) {
  return (
    <ChatBubbleProvider appConfig={APP_CONFIG_DEFAULTS}>
      <AssistantAudio>{children}</AssistantAudio>
    </ChatBubbleProvider>
  );
}

function AssistantAudio({ children }: { children: React.ReactNode }) {
  const { session } = useChatBubble();
  return (
    <CallAudioProvider session={session}>
      <AssistantSession>{children}</AssistantSession>
    </CallAudioProvider>
  );
}

function AssistantSession({ children }: { children: React.ReactNode }) {
  const {
    startSession,
    autoConnecting,
    voiceRequested,
    visitorId,
    resumed,
    setResumed,
    replyLanguage,
    chooseReplyLanguage,
    resetReplyLanguage,
    languagePending,
  } = useChatBubble();
  const session = useSessionContext();
  const { room, isConnected, connectionState } = session;

  useDebugMode({ enabled: IN_DEVELOPMENT });
  useAgentErrors();
  const voiceMode = useVoiceMode();
  useMicOnConnect(voiceRequested && voiceMode !== 'off');
  // The agent's goodbye ends the voice chat only: the mic turns off, the chat stays open.
  useAgentEndCall(() => void room.localParticipant.setMicrophoneEnabled(false));

  const { state: agentState } = useVoiceAssistant();
  const { messages: sessionMessages } = useSessionMessages(session);
  const liveMessages = useVisibleMessages(sessionMessages);
  // Live messages from before the panel switched conversation (history pick, new chat): the
  // ended session's transcript can linger in the room's state, and isn't this conversation's.
  const [hiddenIds, setHiddenIds] = useState<ReadonlySet<string>>(() => new Set());
  const liveMessagesRef = useRef(liveMessages);
  liveMessagesRef.current = liveMessages;
  const hideCurrentLive = useCallback(
    () => setHiddenIds((prev) => new Set([...prev, ...liveMessagesRef.current.map((m) => m.id)])),
    []
  );
  // A guest's ended sessions: kept on screen until a new chat (or a reload), never carried on.
  const [earlier, setEarlier] = useState<ReceivedMessage[]>([]);
  // The conversation id of the guest session that ended last (its chat is in `earlier`).
  const [guestEndedId, setGuestEndedId] = useState<string | null>(null);
  const earlierRef = useRef(earlier);
  earlierRef.current = earlier;
  const messages = useMemo(() => {
    const live =
      hiddenIds.size > 0 ? liveMessages.filter((m) => !hiddenIds.has(m.id)) : liveMessages;
    return [...(resumed ? resumed.messages : earlier), ...live];
  }, [resumed, earlier, liveMessages, hiddenIds]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const { cards, confirm } = useTelcoTopics(room, agentState);
  const greetingDone = useGreetingDone();
  const ready = isConnected && greetingDone;
  const { send } = useChat();
  const { isMicrophoneEnabled } = useLocalParticipant();

  const [queued, setQueued] = useState<string[]>([]);
  const flushingRef = useRef(false);

  const deliver = useCallback(
    async (text: string) => {
      try {
        await send(text);
      } catch (error) {
        console.error('Failed to send chat message:', error);
        toast.error('Message not sent', { description: 'Check your connection and try again.' });
      }
    },
    [send]
  );

  // Once the agent has greeted, the queued text goes out in order.
  useEffect(() => {
    if (!ready || queued.length === 0 || flushingRef.current) return;
    flushingRef.current = true;
    const batch = queued;
    void (async () => {
      for (const text of batch) await deliver(text);
      setQueued((prev) => prev.slice(batch.length));
      flushingRef.current = false;
    })();
  }, [ready, queued, deliver]);

  // A session that ends takes its unsent text with it.
  useEffect(() => {
    const drop = () => setQueued([]);
    room.on(RoomEvent.Disconnected, drop);
    return () => {
      room.off(RoomEvent.Disconnected, drop);
    };
  }, [room]);

  const sendText = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text) return;
      if (ready && queued.length === 0) {
        void deliver(text);
        return;
      }
      setQueued((prev) => [...prev, text]);
      if (connectionState === ConnectionState.Disconnected && !autoConnecting) {
        void startSession({ voice: false, openPanel: false, textStart: true }).then((ok) => {
          if (!ok) setQueued([]);
        });
      }
    },
    [ready, queued.length, deliver, connectionState, autoConnecting, startSession]
  );

  const toggleMic = useCallback(() => {
    if (voiceMode === 'off') return;
    if (connectionState === ConnectionState.Disconnected) {
      if (!autoConnecting) void startSession({ voice: true, openPanel: false });
      return;
    }
    if (!isConnected) return;
    if (isMicrophoneEnabled) {
      void room.localParticipant.setMicrophoneEnabled(false);
    } else {
      void turnOnMicrophone(room);
    }
  }, [
    voiceMode,
    connectionState,
    autoConnecting,
    startSession,
    isConnected,
    isMicrophoneEnabled,
    room,
  ]);

  const end = useCallback(() => void session.end(), [session]);

  const endLive = useCallback(async () => {
    if (session.connectionState === ConnectionState.Disconnected) return;
    try {
      await session.end();
    } catch (error) {
      console.warn('Could not end the assistant session:', error);
    }
  }, [session]);

  const openConversation = useCallback(
    async (id: string): Promise<boolean> => {
      if (!visitorId) return false;
      let detail;
      try {
        detail = await getVisitorConversation(visitorId, id);
      } catch (error) {
        console.error('Failed to load the conversation:', error);
        toast.error('Couldn’t open that chat', { description: 'Please try again.' });
        return false;
      }
      await endLive();
      setQueued([]);
      hideCurrentLive();
      setEarlier([]);
      setGuestEndedId(null);
      setResumed({ id, messages: toReceivedMessages(detail) });
      // It goes on in its own language; a chat from before the pick asks for one.
      resetReplyLanguage(detail.reply_language ?? null);
      setHistoryOpen(false);
      return true;
    },
    [visitorId, endLive, hideCurrentLive, setResumed, resetReplyLanguage]
  );

  const newChat = useCallback(() => {
    void endLive().then(() => {
      setQueued([]);
      hideCurrentLive();
      setEarlier([]);
      setGuestEndedId(null);
      setResumed(null);
      resetReplyLanguage(null);
      setHistoryOpen(false);
    });
  }, [endLive, hideCurrentLive, setResumed, resetReplyLanguage]);

  const startOverForLogin = useCallback(() => {
    const wasLive = session.connectionState !== ConnectionState.Disconnected;
    const voice = isMicrophoneEnabled;
    void endLive().then(() => {
      setQueued([]);
      hideCurrentLive();
      setEarlier([]);
      setGuestEndedId(null);
      setResumed(null);
      setHistoryOpen(false);
      if (wasLive) void startSession({ voice, openPanel: false });
    });
  }, [session, isMicrophoneEnabled, endLive, hideCurrentLive, setResumed, startSession]);

  const me = useOptionalPortalMe();
  const subscriberId = me?.subscriber_id ?? null;
  const subscriberIdRef = useRef(subscriberId);
  subscriberIdRef.current = subscriberId;
  const conversationIdRef = useLastAgentAttribute(room, CONVERSATION_ATTRIBUTE);
  const accountRef = useLastAgentAttribute(room, ACCOUNT_ATTRIBUTE);

  // A customer who logs out (or another who logs in) no longer sees the kept chat.
  const shownForRef = useRef(subscriberId);
  useEffect(() => {
    const before = shownForRef.current;
    shownForRef.current = subscriberId;
    if (before === null || before === subscriberId) return;
    setEarlier([]);
    setGuestEndedId(null);
    setResumed(null);
    resetReplyLanguage(null);
  }, [subscriberId, setResumed, resetReplyLanguage]);

  // A session that ends leaves its chat in the panel until a new one starts (the room drops the
  // live transcript, so what was said is kept here). Signed in, it joins `resumed` and the next
  // session reopens the same conversation. A guest's only stays on screen. A session that
  // belongs to anyone else (a customer's, ended by a logout; a guest's, ended by a login) is
  // dropped.
  const resumedId = resumed?.id ?? null;
  useEffect(() => {
    const keep = () => {
      const said = liveMessagesRef.current;
      if (said.length === 0) return;
      hideCurrentLive();
      const owner = accountRef.current || null;
      const mine = subscriberIdRef.current;
      if (owner !== mine) return;
      if (resumedId) {
        setResumed((prev) =>
          prev?.id === resumedId ? { id: prev.id, messages: [...prev.messages, ...said] } : prev
        );
        return;
      }
      const conversationId = conversationIdRef.current;
      if (mine !== null && conversationId) {
        setResumed({ id: conversationId, messages: [...earlierRef.current, ...said] });
        setEarlier([]);
        setGuestEndedId(null);
      } else {
        setEarlier((prev) => [...prev, ...said]);
        setGuestEndedId(conversationId);
      }
    };
    room.on(RoomEvent.Disconnected, keep);
    return () => {
      room.off(RoomEvent.Disconnected, keep);
    };
  }, [room, resumedId, setResumed, hideCurrentLive, accountRef, conversationIdRef]);

  const connecting =
    !isConnected && (autoConnecting || connectionState === ConnectionState.Connecting);
  const exportableId = isConnected || connecting ? null : (resumedId ?? guestEndedId);

  const value = useMemo<AssistantContextValue>(
    () => ({
      messages,
      historyOpen,
      setHistoryOpen,
      resumedId,
      exportableId,
      openConversation,
      newChat,
      startOverForLogin,
      cards,
      confirm,
      agentState,
      isConnected,
      connecting,
      ready,
      queued,
      sendText,
      micEnabled: isConnected && isMicrophoneEnabled,
      toggleMic,
      voiceMode,
      end,
      replyLanguage,
      chooseReplyLanguage,
      languagePending,
    }),
    [
      messages,
      historyOpen,
      resumedId,
      exportableId,
      openConversation,
      newChat,
      startOverForLogin,
      cards,
      confirm,
      agentState,
      isConnected,
      connecting,
      ready,
      queued,
      sendText,
      isMicrophoneEnabled,
      toggleMic,
      voiceMode,
      end,
      replyLanguage,
      chooseReplyLanguage,
      languagePending,
    ]
  );

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantContextValue {
  const context = useContext(AssistantContext);
  if (!context) throw new Error('useAssistant must be used inside <AssistantProvider>');
  return context;
}

/**
 * For the profile menu's Log out / Switch persona: ends the assistant session (when one is up)
 * so it is gone before the portal session is. A no-op outside the provider.
 */
export function useEndSessionOnLogout(): () => Promise<void> {
  const bubble = useOptionalChatBubble();
  const session = bubble?.session;
  return useCallback(async () => {
    if (!session || session.connectionState === ConnectionState.Disconnected) return;
    try {
      await session.end();
    } catch (error) {
      console.warn('Could not end the assistant session:', error);
    }
  }, [session]);
}
