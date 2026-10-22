'use client';

import { ConnectionState } from 'livekit-client';
import { Loader2Icon } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useSessionContext } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { AgentSessionView_01 } from '@/components/agents-ui/blocks/agent-session-view-01';
import { WelcomeView } from '@/components/app/welcome-view';
import { cn } from '@/lib/shadcn/utils';

const MotionWelcomeView = motion.create(WelcomeView);
const MotionSessionView = motion.create(AgentSessionView_01);

const VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
    },
    hidden: {
      opacity: 0,
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.5,
    ease: 'linear',
  },
};

/** Shown instead of the welcome view while a connect the user didn't press Start for is under
 * way. Its content fades in late, so a quick connect shows nothing at all. */
function ConnectingView({ ref, className }: React.ComponentProps<'div'>) {
  return (
    <div ref={ref} className={className} role="status" aria-live="polite">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.3 }}
        className="text-muted-foreground flex flex-col items-center gap-3 text-sm"
      >
        <Loader2Icon aria-hidden="true" className="size-6 animate-spin" />
        Connecting…
      </motion.div>
    </div>
  );
}

const MotionConnectingView = motion.create(ConnectingView);

interface ViewControllerProps {
  appConfig: AppConfig;
  /** `fullscreen` covers the viewport; `panel` fills its (positioned) container, e.g. the chat
   * bubble's panel. */
  variant?: 'fullscreen' | 'panel';
  /** A connect started on the user's behalf (the chat bubble opening, or joining `?room=`) is
   * under way or about to begin: show a neutral connecting state, not the Start call screen.
   * Set it before calling start(), since the connection state is still Disconnected until the
   * session gets going. */
  autoConnecting?: boolean;
}

export function ViewController({
  appConfig,
  variant = 'fullscreen',
  autoConnecting = false,
}: ViewControllerProps) {
  const { isConnected, connectionState, start } = useSessionContext();
  const isPanel = variant === 'panel';
  const showConnecting = !isConnected && autoConnecting;

  return (
    <AnimatePresence mode="wait">
      {/* Connecting (started automatically) */}
      {showConnecting && (
        <MotionConnectingView
          key="connecting"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: 'linear' }}
          className={cn(isPanel && 'grid h-full place-content-center')}
        />
      )}
      {/* Welcome view */}
      {!isConnected && !showConnecting && (
        <MotionWelcomeView
          key="welcome"
          {...VIEW_MOTION_PROPS}
          startButtonText={appConfig.startButtonText}
          connecting={connectionState === ConnectionState.Connecting}
          // Connect with the mic off; AppSetup (useMicOnConnect) turns it on once connected.
          onStartCall={() => start({ tracks: { microphone: { enabled: false } } })}
          className={cn(isPanel && 'grid h-full place-content-center px-4')}
        />
      )}
      {/* Session view */}
      {isConnected && (
        <MotionSessionView
          key="session-view"
          {...VIEW_MOTION_PROPS}
          supportsChatInput={appConfig.supportsChatInput}
          companyName={appConfig.companyName}
          className={isPanel ? 'absolute inset-0' : 'fixed inset-0'}
        />
      )}
    </AnimatePresence>
  );
}
