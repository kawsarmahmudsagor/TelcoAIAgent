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
import { ConnectionState, type Room, TokenSource } from 'livekit-client';
import { toast } from 'sonner';
import { type ReceivedMessage, type UseSessionReturn, useSession } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { getSandboxTokenSource } from '@/lib/utils';
import { useVisitorId, useVisitorSessionOptions } from '@/lib/visitor-id';

/** The LiveKit token source: the sandbox endpoint when configured, else our /api/token route. */
function useAppTokenSource(appConfig: AppConfig) {
  return useMemo(() => {
    return typeof process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string'
      ? getSandboxTokenSource(appConfig)
      : TokenSource.endpoint('/api/token');
  }, [appConfig]);
}

/** The panel's element id, for `aria-controls`. */
export const CHAT_PANEL_ID = 'chat-bubble-panel';

/** An earlier chat picked from the history: shown above the live transcript and carried on. */
export interface ResumedConversation {
  id: string;
  messages: ReceivedMessage[];
}

export interface StartSessionOptions {
  /** Turn the mic on once connected (a voice chat); otherwise the session is text-only. */
  voice: boolean;
  /** Show the bubble's panel once connected. */
  openPanel: boolean;
  /** A typed message opens the session: the agent answers it instead of greeting. */
  textStart?: boolean;
}

interface ChatBubbleContextValue {
  /** Whether the bubble's panel is showing. A closed panel is hidden, never unmounted. */
  isOpen: boolean;
  /** Shows the panel (connected or not). */
  open: () => void;
  /**
   * Starts the session; during one it only shows the panel (when asked to). Resolves once
   * connected, or false when the connect failed (already toasted).
   */
  startSession: (options: StartSessionOptions) => Promise<boolean>;
  /**
   * Starts a text session whose agent opens with the greeting for this notification: a live
   * session is ended first. Resolves once connected, or false when the connect failed.
   */
  startNudgeSession: (nudgeId: string) => Promise<boolean>;
  /** A voice call that shows the panel: `startSession({ voice: true, openPanel: true })`. */
  startCall: () => void;
  /** A session started by startSession() is connecting. */
  autoConnecting: boolean;
  /** The current (or connecting) session was started for voice: the mic goes on at connect. */
  voiceRequested: boolean;
  /** Hides the panel; the session keeps running. */
  close: () => void;
  /**
   * Whether the panel fills the viewport (from `sm` up; below it the panel is always a sheet).
   * Always true during a call: the call has no docked size.
   */
  isFullscreen: boolean;
  toggleFullscreen: () => void;
  /** Back to the docked panel size; during a call it minimises the panel instead. */
  exitFullscreen: () => void;
  /** This browser's anonymous visitor id (null until mounted), for the chat history. */
  visitorId: string | null;
  /**
   * The earlier chat being carried on, if any: the next session's agent reopens it (no
   * greeting) and its messages show above the live ones. Set while disconnected.
   */
  resumed: ResumedConversation | null;
  setResumed: React.Dispatch<React.SetStateAction<ResumedConversation | null>>;
  /** The session's room, e.g. for setting participant attributes from a page. */
  room: Room;
  isConnected: boolean;
  /** The one agent session, for the provider that hands it to the agent UI. */
  session: UseSessionReturn;
}

const ChatBubbleContext = createContext<ChatBubbleContextValue | null>(null);

/**
 * Owns the agent session and the bubble's open state. The portal layout wraps its whole shell in
 * it (through AssistantProvider), so pages never remount it: one session survives client
 * navigation, and the bubble and the full assistant page show the same conversation.
 */
export function ChatBubbleProvider({
  appConfig,
  children,
}: {
  appConfig: AppConfig;
  children: React.ReactNode;
}) {
  const tokenSource = useAppTokenSource(appConfig);
  const visitorId = useVisitorId();
  // The notification a session is being started for; cleared once connected so the next session
  // is a normal one.
  const [nudgeId, setNudgeId] = useState<string | null>(null);
  const pendingNudgeRef = useRef<((ok: boolean) => void) | null>(null);
  // Whether the latest start was a typed message's. It rides in the token request, so a start
  // that changes it waits for the options to re-render first (deferredStartRef).
  const [textStart, setTextStart] = useState(false);
  const deferredStartRef = useRef<{
    options: StartSessionOptions;
    resolve: (ok: boolean) => void;
  } | null>(null);
  const [resumed, setResumed] = useState<ResumedConversation | null>(null);
  const sessionOptions = useVisitorSessionOptions(
    appConfig.agentName,
    visitorId,
    nudgeId,
    textStart,
    resumed?.id ?? null
  );
  const session = useSession(tokenSource, sessionOptions);
  const [isOpen, setIsOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const isConnected = session.isConnected;
  const [autoConnecting, setAutoConnecting] = useState(false);
  const [openWhenConnected, setOpenWhenConnected] = useState(false);
  const [voiceRequested, setVoiceRequested] = useState(false);

  const startSession = useCallback(
    async (options: StartSessionOptions): Promise<boolean> => {
      const { voice, openPanel, textStart: typed = false } = options;
      if (session.connectionState !== ConnectionState.Disconnected) {
        if (openPanel) setIsOpen(true);
        return true;
      }
      if (typed !== textStart) {
        // Connecting already, as far as callers can tell (no second start meanwhile).
        setAutoConnecting(true);
        return new Promise<boolean>((resolve) => {
          deferredStartRef.current?.resolve(false);
          deferredStartRef.current = { options, resolve };
          setTextStart(typed);
        });
      }
      setVoiceRequested(voice);
      setOpenWhenConnected(openPanel);
      setAutoConnecting(true);
      try {
        // Connect with the mic off; useMicOnConnect turns it on once connected (voice only).
        await session.start({ tracks: { microphone: { enabled: false } } });
        return true;
      } catch (error: unknown) {
        console.error('Failed to start the assistant session:', error);
        toast.error('Couldn’t reach the assistant', { description: 'Please try again.' });
        setAutoConnecting(false);
        return false;
      }
    },
    [session, textStart]
  );

  // The token options carry the new textStart by now (useSession's effect runs first): start.
  useEffect(() => {
    const deferred = deferredStartRef.current;
    if (!deferred || (deferred.options.textStart ?? false) !== textStart) return;
    deferredStartRef.current = null;
    void startSession(deferred.options).then(deferred.resolve);
  }, [textStart, startSession]);

  const startCall = useCallback(
    () => void startSession({ voice: true, openPanel: true }),
    [startSession]
  );

  const startNudgeSession = useCallback(
    async (id: string): Promise<boolean> => {
      if (session.connectionState !== ConnectionState.Disconnected) {
        try {
          await session.end();
        } catch (error) {
          console.warn('Could not end the assistant session:', error);
        }
      }
      return new Promise<boolean>((resolve) => {
        pendingNudgeRef.current?.(false);
        pendingNudgeRef.current = resolve;
        // A notification opens a new conversation, not the one picked from the history.
        setResumed(null);
        setNudgeId(id);
      });
    },
    [session]
  );

  // The session options carry the nudge by now and the old session is gone: connect.
  const connectionState = session.connectionState;
  useEffect(() => {
    const resolve = pendingNudgeRef.current;
    if (!resolve || !nudgeId || connectionState !== ConnectionState.Disconnected) return;
    pendingNudgeRef.current = null;
    void startSession({ voice: false, openPanel: false }).then((ok) => {
      if (!ok) setNudgeId(null);
      resolve(ok);
    });
  }, [nudgeId, connectionState, startSession]);

  useEffect(() => {
    if (isConnected && nudgeId && !pendingNudgeRef.current) setNudgeId(null);
  }, [isConnected, nudgeId]);

  // Connected: show the panel if the start asked for it. Disconnected: leave fullscreen.
  useEffect(() => {
    if (!isConnected) {
      setIsFullscreen(false);
    } else if (autoConnecting) {
      if (openWhenConnected) setIsOpen(true);
      setAutoConnecting(false);
    }
  }, [isConnected, autoConnecting, openWhenConnected]);
  const toggleFullscreen = useCallback(() => setIsFullscreen((fullscreen) => !fullscreen), []);
  const exitFullscreen = useCallback(() => {
    if (isConnected) setIsOpen(false);
    else setIsFullscreen(false);
  }, [isConnected]);

  const value = useMemo<ChatBubbleContextValue>(
    () => ({
      isOpen,
      open,
      startSession,
      startNudgeSession,
      startCall,
      autoConnecting,
      voiceRequested,
      close,
      isFullscreen: isFullscreen || isConnected,
      toggleFullscreen,
      exitFullscreen,
      visitorId,
      resumed,
      setResumed,
      room: session.room,
      isConnected,
      session,
    }),
    [
      isOpen,
      open,
      startSession,
      startNudgeSession,
      startCall,
      autoConnecting,
      voiceRequested,
      close,
      isFullscreen,
      toggleFullscreen,
      exitFullscreen,
      visitorId,
      resumed,
      isConnected,
      session,
    ]
  );

  return <ChatBubbleContext.Provider value={value}>{children}</ChatBubbleContext.Provider>;
}

/** The bubble's context, or null outside the provider (e.g. the standalone /chat page). */
export function useOptionalChatBubble(): ChatBubbleContextValue | null {
  return useContext(ChatBubbleContext);
}

export function useChatBubble(): ChatBubbleContextValue {
  const context = useContext(ChatBubbleContext);
  if (!context) throw new Error('useChatBubble must be used inside <ChatBubbleProvider>');
  return context;
}
