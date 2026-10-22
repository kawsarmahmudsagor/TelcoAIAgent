'use client';

import React, { useMemo, useRef, useState } from 'react';
import { PresenceContext } from 'motion/react';
import {
  useIsSpeaking,
  useLocalParticipant,
  useSessionContext,
  useSessionMessages,
  useVoiceAssistant,
} from '@livekit/components-react';
import { ApartmentShortlist, placeShortlistResults } from '@/components/app/apartment-shortlist';
import { useCallAudio } from '@/components/app/call/call-audio-provider';
import { type CallActivity, CallAvatar } from '@/components/app/call/call-avatar';
import { ConversationButton } from '@/components/app/call/call-chat';
import { CallControls } from '@/components/app/call/call-controls';
import { CallOverlay } from '@/components/app/call/call-overlay';
import { CallWaveform } from '@/components/app/call/call-waveform';
import { ConversationPane } from '@/components/app/call/conversation-pane';
import { statusLabel } from '@/components/app/call/status';
import { useAgentEndCall } from '@/hooks/useAgentEndCall';
import {
  type ShortlistResult,
  useApartmentShortlist,
  useBookingForm,
  useVisibleMessages,
} from '@/lib/livekit-text-streams';
import { cn } from '@/lib/shadcn/utils';

const CONVERSATION_ID = 'call-conversation';

export interface AgentSessionView_01Props {
  /**
   * Shows the chat bubble that opens the Conversation UI (transcript and message box).
   *
   * @default true
   */
  supportsChatInput?: boolean;
  /** The agency's name, for the caption under the avatar ("Your Horizon Realty agent"). */
  companyName?: string;
  /** Optional class name merged onto the outer `<section>` container. */
  className?: string;
}

/**
 * The in-call screen. The Call UI: the agent's avatar with voice animations, Mic / End call /
 * Speaker, and the latest search result or a booking form over the call. Its chat bubble opens
 * the Conversation UI, the call's transcript and message box, in a pane on the right. Always
 * dark. Lays itself out by its own width (`@container`).
 */
export function AgentSessionView_01({
  supportsChatInput = true,
  companyName,
  ref,
  className,
  ...props
}: React.ComponentProps<'section'> & AgentSessionView_01Props) {
  const session = useSessionContext();
  const { state: agentState, audioTrack: agentTrack } = useVoiceAssistant();
  const micTrack = session.local.microphoneTrack;
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const userSpeaking = useIsSpeaking(localParticipant);
  const { muted: speakerMuted } = useCallAudio();
  // The agent ends the call after its goodbye, the way the End call button does.
  useAgentEndCall(() => void session.end());

  // Mounted once for the whole call, whether or not the conversation is open: livekit-client
  // allows one handler per topic, and the transcript has to collect turns all along.
  const { messages: sessionMessages } = useSessionMessages(session);
  const messages = useVisibleMessages(sessionMessages);
  const { results: shortlistResults, dismiss: dismissShortlist } = useApartmentShortlist();
  const bookingForms = useBookingForm();

  // The conversation shows every search result, each after the turn it belongs to.
  const placement = useMemo(
    () => placeShortlistResults(messages, shortlistResults),
    [messages, shortlistResults]
  );
  const renderResults = (results: ShortlistResult[] | undefined) =>
    results?.length
      ? results.map((result) => (
          <ApartmentShortlist key={result.id} result={result} onDismiss={dismissShortlist} />
        ))
      : undefined;

  const activity: CallActivity =
    agentState === 'speaking'
      ? 'agent'
      : userSpeaking && isMicrophoneEnabled && agentState === 'listening'
        ? 'user'
        : null;

  const [conversationOpen, setConversationOpen] = useState(false);
  const conversationButtonRef = useRef<HTMLButtonElement>(null);
  const [overlayVisible, setOverlayVisible] = useState(false);

  return (
    <section
      ref={ref}
      data-surface="call"
      aria-label="Call"
      className={cn(
        'dark bg-background text-foreground @container/call-root relative isolate flex h-full w-full overflow-hidden',
        className
      )}
      {...props}
    >
      {/*
        Cut the inside off from the view switcher's AnimatePresence (view-controller.tsx): when
        the call ends, only this section's own fade should gate the Start screen. Otherwise every
        listing card with an `exit` variant joins in, and a card that re-mounts as the transcript
        resets on disconnect never reports done -- the switch hangs on a blank panel.
      */}
      <PresenceContext.Provider value={null}>
        {/* Call UI */}
        <div className="@container relative flex min-w-0 flex-1 flex-col">
          {/* A low evergreen glow behind the agent. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_70%_55%_at_50%_36%,color-mix(in_oklch,var(--primary)_12%,transparent),transparent_70%)]"
          />

          {/* Stage */}
          <div className="relative min-h-0 flex-1">
            <div
              className={cn(
                'flex h-full flex-col items-center justify-center px-4 transition-[padding] duration-300 ease-out',
                // Make room for the result column, so it never covers the agent.
                overlayVisible && '@5xl:pl-[468px]'
              )}
            >
              <div className="p-10 @5xl:p-16 [@media(max-height:500px)]:p-4">
                <CallAvatar
                  activity={activity}
                  agentState={agentState}
                  agentTrack={agentTrack}
                  micTrack={micTrack}
                  speakerMuted={speakerMuted}
                  className="w-28 @5xl:w-48 [@media(max-height:500px)]:w-16"
                />
              </div>
              <div className="text-center">
                <p className="font-display text-xl font-semibold tracking-tight @5xl:text-[1.75rem]">
                  Your {companyName ? `${companyName} ` : ''}agent
                </p>
                <p role="status" aria-live="polite" className="text-muted-foreground mt-1 text-sm">
                  {statusLabel(agentState)}
                  {speakerMuted && <span className="text-brass block text-xs">Speaker off</span>}
                </p>
              </div>
              <CallWaveform
                activity={activity}
                agentState={agentState}
                agentTrack={agentTrack}
                micTrack={micTrack}
                speakerMuted={speakerMuted}
                className="mt-4 @5xl:mt-8"
              />
            </div>

            <CallOverlay
              results={shortlistResults}
              forms={bookingForms}
              onVisibleChange={setOverlayVisible}
            />
          </div>

          {/* Dock */}
          <div className="relative grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-2 px-3 pb-4 @5xl:px-6 @5xl:pb-8">
            <span />
            <CallControls onEndCall={() => void session.end()} />
            {supportsChatInput && (
              <ConversationButton
                ref={conversationButtonRef}
                open={conversationOpen}
                onOpenChange={setConversationOpen}
                controls={CONVERSATION_ID}
                className="justify-self-end"
              />
            )}
          </div>
        </div>

        {/* Conversation UI */}
        {supportsChatInput && (
          <ConversationPane
            id={CONVERSATION_ID}
            open={conversationOpen}
            onClose={() => {
              setConversationOpen(false);
              conversationButtonRef.current?.focus();
            }}
            agentState={agentState}
            messages={messages}
            renderAfterMessage={(message) => renderResults(placement.byMessageId.get(message.id))}
            trailingContent={renderResults(placement.unplaced)}
          />
        )}
      </PresenceContext.Provider>
    </section>
  );
}
