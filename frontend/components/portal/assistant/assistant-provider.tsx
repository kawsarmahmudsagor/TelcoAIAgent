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
import { ConnectionState, RoomEvent } from 'livekit-client';
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
import { useAgentEndCall } from '@/hooks/useAgentEndCall';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { turnOnMicrophone, useMicOnConnect } from '@/hooks/useMicOnConnect';
import { useGreetingDone, useVisibleMessages } from '@/lib/livekit-text-streams';
import { getVisitorConversation, toReceivedMessages } from '@/lib/public-conversations';
import { type ConfirmState, type TelcoCard, useTelcoTopics } from '@/lib/telco-topics';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

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
   * Loads an earlier chat from the history and carries it on: a live session is ended first,
   * and the next one reopens that conversation. Resolves false when it couldn't be loaded.
   */
  openConversation(id: string): Promise<boolean>;
  /** Ends any live session and clears the panel for a new conversation. */
  newChat(): void;
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
  const { startSession, autoConnecting, voiceRequested, visitorId, resumed, setResumed } =
    useChatBubble();
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
    () => setHiddenIds(new Set(liveMessagesRef.current.map((m) => m.id))),
    []
  );
  const messages = useMemo(() => {
    const live =
      hiddenIds.size > 0 ? liveMessages.filter((m) => !hiddenIds.has(m.id)) : liveMessages;
    return resumed ? [...resumed.messages, ...live] : live;
  }, [resumed, liveMessages, hiddenIds]);
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
      setResumed({ id, messages: toReceivedMessages(detail) });
      setHistoryOpen(false);
      return true;
    },
    [visitorId, endLive, hideCurrentLive, setResumed]
  );

  const newChat = useCallback(() => {
    void endLive().then(() => {
      setQueued([]);
      hideCurrentLive();
      setResumed(null);
      setHistoryOpen(false);
    });
  }, [endLive, hideCurrentLive, setResumed]);

  // A carried-on chat whose session ends: the room drops the live transcript, so what was said
  // joins the stored messages (the next session reopens the same conversation).
  const resumedId = resumed?.id ?? null;
  useEffect(() => {
    if (!resumedId) return;
    const keep = () => {
      const said = liveMessagesRef.current;
      if (said.length === 0) return;
      setResumed((prev) =>
        prev?.id === resumedId ? { id: prev.id, messages: [...prev.messages, ...said] } : prev
      );
    };
    room.on(RoomEvent.Disconnected, keep);
    return () => {
      room.off(RoomEvent.Disconnected, keep);
    };
  }, [room, resumedId, setResumed]);

  const value = useMemo<AssistantContextValue>(
    () => ({
      messages,
      historyOpen,
      setHistoryOpen,
      resumedId,
      openConversation,
      newChat,
      cards,
      confirm,
      agentState,
      isConnected,
      connecting:
        !isConnected && (autoConnecting || connectionState === ConnectionState.Connecting),
      ready,
      queued,
      sendText,
      micEnabled: isConnected && isMicrophoneEnabled,
      toggleMic,
      voiceMode,
      end,
    }),
    [
      messages,
      historyOpen,
      resumedId,
      openConversation,
      newChat,
      cards,
      confirm,
      agentState,
      isConnected,
      autoConnecting,
      connectionState,
      ready,
      queued,
      sendText,
      isMicrophoneEnabled,
      toggleMic,
      voiceMode,
      end,
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
