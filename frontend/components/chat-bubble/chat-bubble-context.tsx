'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ConnectionState, type Room } from 'livekit-client';
import { toast } from 'sonner';
import { type UseSessionReturn, useSession } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { useAppTokenSource } from '@/components/app/app';
import { useVisitorId, useVisitorSessionOptions } from '@/lib/visitor-id';

/** The panel's element id, for `aria-controls`. */
export const CHAT_PANEL_ID = 'chat-bubble-panel';

export interface StartSessionOptions {
  /** Turn the mic on once connected (a voice chat); otherwise the session is text-only. */
  voice: boolean;
  /** Show the bubble's panel once connected. */
  openPanel: boolean;
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
  const sessionOptions = useVisitorSessionOptions(appConfig.agentName, visitorId);
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
    async ({ voice, openPanel }: StartSessionOptions): Promise<boolean> => {
      if (session.connectionState !== ConnectionState.Disconnected) {
        if (openPanel) setIsOpen(true);
        return true;
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
    [session]
  );
  const startCall = useCallback(
    () => void startSession({ voice: true, openPanel: true }),
    [startSession]
  );

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
      startCall,
      autoConnecting,
      voiceRequested,
      close,
      isFullscreen: isFullscreen || isConnected,
      toggleFullscreen,
      exitFullscreen,
      visitorId,
      room: session.room,
      isConnected,
      session,
    }),
    [
      isOpen,
      open,
      startSession,
      startCall,
      autoConnecting,
      voiceRequested,
      close,
      isFullscreen,
      toggleFullscreen,
      exitFullscreen,
      visitorId,
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
