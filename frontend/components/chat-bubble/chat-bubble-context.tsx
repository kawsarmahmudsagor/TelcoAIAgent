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

interface ChatBubbleContextValue {
  /**
   * Whether the chat panel is showing; only ever during a call. A closed panel is hidden, never
   * unmounted.
   */
  isOpen: boolean;
  /** Shows the panel of the call in progress (no-op outside a call). */
  open: () => void;
  /** Starts a call and shows the panel once it's connected; during a call, just shows it. */
  startCall: () => void;
  /** A call started by startCall() is connecting: the launcher shows a spinner. */
  autoConnecting: boolean;
  /** Hides the panel; the call keeps running. */
  close: () => void;
  /**
   * Whether the panel fills the viewport (from `sm` up; below it the panel is always a sheet).
   * Always true during a call: the call has no docked size.
   */
  isFullscreen: boolean;
  toggleFullscreen: () => void;
  /**
   * Back to the docked panel size, e.g. when a listing card opens its page behind the chat.
   * During a call, which is always fullscreen, it minimises the panel instead (the call goes on).
   */
  exitFullscreen: () => void;
  /** This browser's anonymous visitor id (null until mounted), for the chat history. */
  visitorId: string | null;
  /** The session's room, e.g. for setting participant attributes from a page. */
  room: Room;
  isConnected: boolean;
  /** For ChatBubble only: the session it provides to the agent UI. */
  session: UseSessionReturn;
}

const ChatBubbleContext = createContext<ChatBubbleContextValue | null>(null);

/**
 * Owns the public site's agent session and the bubble's open state. It wraps the (site) layout's
 * children and the ChatBubble as a plain context provider, so pages never remount and the call
 * survives client navigation between public pages.
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
  const startCall = useCallback(() => {
    if (session.connectionState !== ConnectionState.Disconnected) {
      setIsOpen(true);
      return;
    }
    // The panel opens once connected (effect below), so the docked Start call screen never
    // shows in between; meanwhile the launcher shows a spinner.
    setAutoConnecting(true);
    // Connect with the mic off; AppSetup (useMicOnConnect) turns it on once connected.
    session.start({ tracks: { microphone: { enabled: false } } }).catch((error: unknown) => {
      console.error('Failed to start the call:', error);
      toast.error('Couldn’t start the call', { description: 'Please try again.' });
      setAutoConnecting(false);
    });
  }, [session]);

  // Connected: show the call. Disconnected (the call ended): close the panel, so the launcher
  // goes back to the phone icon instead of leaving the Start call screen up.
  useEffect(() => {
    if (!isConnected) {
      setIsOpen(false);
      setIsFullscreen(false);
    } else if (autoConnecting) {
      setIsOpen(true);
      setAutoConnecting(false);
    }
  }, [isConnected, autoConnecting]);
  const toggleFullscreen = useCallback(() => setIsFullscreen((fullscreen) => !fullscreen), []);
  const exitFullscreen = useCallback(() => {
    if (isConnected) setIsOpen(false);
    else setIsFullscreen(false);
  }, [isConnected]);

  const value = useMemo<ChatBubbleContextValue>(
    () => ({
      // The panel only shows during a call (also covers the render before the effect closes it).
      isOpen: isOpen && isConnected,
      open,
      startCall,
      autoConnecting,
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
      startCall,
      autoConnecting,
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

/** The bubble's context, or null outside the public site (e.g. the standalone /chat page). */
export function useOptionalChatBubble(): ChatBubbleContextValue | null {
  return useContext(ChatBubbleContext);
}

export function useChatBubble(): ChatBubbleContextValue {
  const context = useContext(ChatBubbleContext);
  if (!context) throw new Error('useChatBubble must be used inside <ChatBubbleProvider>');
  return context;
}
