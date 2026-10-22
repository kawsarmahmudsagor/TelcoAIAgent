'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ConnectionState, TokenSource } from 'livekit-client';
import { toast } from 'sonner';
import { useSession } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { CallAudioProvider } from '@/components/app/call/call-audio-provider';
import { ViewController } from '@/components/app/view-controller';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { useMicOnConnect } from '@/hooks/useMicOnConnect';
import { getSandboxTokenSource } from '@/lib/utils';
import { useVisitorId, useVisitorSessionOptions } from '@/lib/visitor-id';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

/** Session-wide side effects; render once inside an AgentSessionProvider. */
export function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });
  useAgentErrors();
  useMicOnConnect();

  return null;
}

/** The LiveKit token source: the sandbox endpoint when configured, else our /api/token route. */
export function useAppTokenSource(appConfig: AppConfig) {
  return useMemo(() => {
    return typeof process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string'
      ? getSandboxTokenSource(appConfig)
      : TokenSource.endpoint('/api/token');
  }, [appConfig]);
}

interface AppProps {
  appConfig: AppConfig;
}

/** Full-screen session UI of the standalone chat page (app/(widget)/chat), which the dashboard
 * also uses to answer a scheduled cold call (`?room=`). The page's layout provides the <Toaster>. */
export function App({ appConfig }: AppProps) {
  const tokenSource = useAppTokenSource(appConfig);

  // `?room=<name>` means we're joining a room that already exists and already
  // has its agent dispatched (e.g. the admin dashboard jumping straight into
  // a scheduled cold call the moment it fires) -- join it directly instead of
  // requesting a fresh inbound-chat room + dispatch.
  const searchParams = useSearchParams();
  const existingRoomName = searchParams.get('room') ?? undefined;

  // A new chat records this browser's visitor id (see the chat bubble's history); joining a
  // dashboard cold-call room doesn't.
  const visitorId = useVisitorId();
  const chatOptions = useVisitorSessionOptions(appConfig.agentName, visitorId);
  const session = useSession(
    tokenSource,
    existingRoomName ? { roomName: existingRoomName } : chatOptions
  );

  // Skip the welcome screen and connect immediately when joining an existing
  // room -- this should feel like receiving the call, not starting one. True
  // from the first render, so the Start call screen never flashes before the
  // effect below gets the connect going.
  const [autoJoining, setAutoJoining] = useState(Boolean(existingRoomName));
  const autoStartedRef = useRef(false);
  useEffect(() => {
    if (
      existingRoomName &&
      !autoStartedRef.current &&
      session.connectionState === ConnectionState.Disconnected
    ) {
      autoStartedRef.current = true;
      // Connect with the mic off; AppSetup turns it on once connected.
      session
        .start({ tracks: { microphone: { enabled: false } } })
        .catch((error: unknown) => {
          console.error('Failed to join the call:', error);
          toast.error('Couldn’t join the call', { description: 'Please try again.' });
        })
        // Resolves once connected; after a failure the Start call screen offers a retry.
        .finally(() => setAutoJoining(false));
    }
  }, [existingRoomName, session]);

  // A scheduled call that was connected and has ended (End call, or the agent hung up) has
  // nothing left to show: the room is gone, so go to the site's home page.
  const router = useRouter();
  const wasConnectedRef = useRef(false);
  useEffect(() => {
    if (!existingRoomName) return;
    if (session.connectionState === ConnectionState.Connected) {
      wasConnectedRef.current = true;
    } else if (
      wasConnectedRef.current &&
      session.connectionState === ConnectionState.Disconnected
    ) {
      router.replace('/home');
    }
  }, [existingRoomName, session.connectionState, router]);

  return (
    <CallAudioProvider session={session}>
      <AppSetup />
      <main className="grid h-svh grid-cols-1 place-content-center">
        <ViewController appConfig={appConfig} autoConnecting={autoJoining} />
      </main>
      <StartAudioButton label="Start Audio" />
    </CallAudioProvider>
  );
}
