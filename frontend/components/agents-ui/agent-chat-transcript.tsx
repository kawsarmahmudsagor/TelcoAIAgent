'use client';

import { type ComponentProps, Fragment, type ReactNode } from 'react';
import { Streamdown } from 'streamdown';
import { type AgentState, type ReceivedMessage } from '@livekit/components-react';
import { AgentChatIndicator } from '@/components/agents-ui/agent-chat-indicator';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import { Marker, MarkerContent, MarkerIcon } from '@/components/ui/marker';
import { Message, MessageContent } from '@/components/ui/message';
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '@/components/ui/message-scroller';

/**
 * Props for the AgentChatTranscript component.
 */
export interface AgentChatTranscriptProps
  extends ComponentProps<'div'>,
    ComponentProps<typeof MessageScrollerProvider>,
    ComponentProps<typeof MessageScrollerViewport>,
    ComponentProps<typeof MessageScrollerContent> {
  /**
   * Whether to automatically scroll to the bottom of the transcript when new messages are added.
   * @defaultValue true
   */
  autoScroll?: boolean;
  /**
   * The scroll anchor to use when auto-scrolling.
   * @defaultValue false
   */
  scrollAnchor?: boolean | 'user' | 'other' | 'any';
  /**
   * The scroll button render function
   */
  scrollButtonRender?: ComponentProps<typeof MessageScrollerButton>['render'];
  /**
   * The scroll button behavior
   */
  scrollButtonBehavior?: ComponentProps<typeof MessageScrollerButton>['behavior'];
  /**
   * The scroll button direction
   */
  scrollButtonDirection?: ComponentProps<typeof MessageScrollerButton>['direction'];
  /**
   * The current state of the agent. When 'thinking', displays a loading indicator.
   */
  agentState?: AgentState;
  /**
   * Array of messages to display in the transcript.
   * @defaultValue []
   */
  messages?: ReceivedMessage[];
  /**
   * Extra content rendered as the last item in the scrollable transcript, after all
   * messages but before the "thinking" indicator -- e.g. structured results the agent
   * produced (like a search result list) that should read as part of the conversation.
   */
  trailingContent?: ReactNode;
  /**
   * Extra content rendered directly after a given message (e.g. a search result list
   * pinned to the turn it belongs to), so it keeps its place as the conversation grows.
   */
  renderAfterMessage?: (message: ReceivedMessage) => ReactNode;
  /**
   * Additional CSS class names to apply to the conversation container.
   */
  className?: string;
}

/**
 * A chat transcript component that displays a conversation between the user and agent.
 * Shows messages with timestamps and origin indicators, plus a thinking indicator
 * when the agent is processing.
 *
 * @extends ComponentProps<'div'>, ComponentProps<typeof MessageScrollerProvider>, ComponentProps<typeof MessageScrollerViewport>, ComponentProps<typeof MessageScrollerContent>
 *
 *
 * @example
 * ```tsx
 * <AgentChatTranscript
 *   agentState={agentState}
 *   messages={chatMessages}
 * />
 * ```
 */
export function AgentChatTranscript({
  scrollAnchor,
  autoScroll = true,
  scrollMargin,
  scrollEdgeThreshold,
  preserveScrollOnPrepend,
  scrollPreviousItemPeek,
  defaultScrollPosition = 'last-anchor',
  scrollButtonRender,
  scrollButtonBehavior,
  scrollButtonDirection,
  spacerClassName,
  agentState,
  messages = [],
  trailingContent,
  renderAfterMessage,
  className,
  ...props
}: AgentChatTranscriptProps) {
  return (
    <MessageScrollerProvider
      autoScroll={autoScroll}
      scrollMargin={scrollMargin}
      defaultScrollPosition={defaultScrollPosition}
      scrollEdgeThreshold={scrollEdgeThreshold}
      scrollPreviousItemPeek={scrollPreviousItemPeek}
    >
      <MessageScroller className={className} {...props}>
        <MessageScrollerViewport preserveScrollOnPrepend={preserveScrollOnPrepend}>
          <MessageScrollerContent
            spacerClassName={spacerClassName}
            aria-busy={agentState === 'thinking'}
          >
            {messages.map((receivedMessage) => {
              const { id, timestamp, from, message } = receivedMessage;
              const time = new Date(timestamp);
              const isUser = from?.isLocal;
              const locale = typeof navigator !== 'undefined' ? navigator.language : 'en-US';
              const title = time.toLocaleTimeString(locale, { timeStyle: 'full' });
              let _scrollAnchor = false;

              if (
                scrollAnchor === 'any' ||
                (scrollAnchor === 'user' && isUser) ||
                (scrollAnchor === 'other' && !isUser)
              ) {
                _scrollAnchor = true;
              }

              const afterContent = renderAfterMessage?.(receivedMessage);

              return (
                <Fragment key={id}>
                  <MessageScrollerItem messageId={id} scrollAnchor={_scrollAnchor}>
                    <Message align={isUser ? 'end' : 'start'} title={title}>
                      <MessageContent>
                        <Bubble
                          align={isUser ? 'end' : 'start'}
                          variant={isUser ? 'secondary' : 'ghost'}
                        >
                          <BubbleContent>
                            <Streamdown>{message}</Streamdown>
                          </BubbleContent>
                        </Bubble>
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                  {/* See the content-visibility note on trailingContent below. */}
                  {afterContent && (
                    <MessageScrollerItem className="[content-visibility:visible]">
                      {afterContent}
                    </MessageScrollerItem>
                  )}
                </Fragment>
              );
            })}

            {/*
              Every MessageScrollerItem gets `content-visibility: auto` with a
              10rem intrinsic-size placeholder (see message-scroller.tsx) so
              off-screen chat bubbles skip layout for perf. That estimate is
              harmless for a couple lines of text, but the apartment shortlist
              can be 500-600px+ tall -- the browser renders it at the 160px
              placeholder height, then snaps to its real height the moment
              content-visibility decides it needs to actually lay it out. That
              snap is the jitter: verified by polling this item's rect every
              frame, which showed height jump 0 -> 160 (the placeholder) ->
              its true ~550px in discrete, unanimated steps. Forcing this one
              item to always render for real removes the placeholder stage
              entirely, leaving a single clean reflow instead of two.
            */}
            {trailingContent && (
              <MessageScrollerItem className="[content-visibility:visible]">
                {trailingContent}
              </MessageScrollerItem>
            )}

            {/* Agent is thinking indicator */}
            {agentState === 'thinking' && (
              <MessageScrollerItem>
                <Marker role="status">
                  <MarkerIcon>
                    <AgentChatIndicator size="sm" />
                  </MarkerIcon>
                  <MarkerContent className="shimmer">Thinking...</MarkerContent>
                </Marker>
              </MessageScrollerItem>
            )}
          </MessageScrollerContent>
        </MessageScrollerViewport>

        {/* Scroll to bottom button */}
        <MessageScrollerButton
          variant="outline"
          className="rounded-full"
          render={scrollButtonRender}
          behavior={scrollButtonBehavior}
          direction={scrollButtonDirection}
        />
      </MessageScroller>
    </MessageScrollerProvider>
  );
}
