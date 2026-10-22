'use client';

import type { ReactNode } from 'react';
import { XIcon } from 'lucide-react';
import type { AgentState, ReceivedMessage } from '@livekit/components-react';
import { AgentChatTranscript } from '@/components/agents-ui/agent-chat-transcript';
import { cn } from '@/lib/shadcn/utils';
import { ChatComposer } from './call-chat';

interface ConversationPaneProps {
  id: string;
  open: boolean;
  onClose: () => void;
  agentState: AgentState;
  messages: ReceivedMessage[];
  renderAfterMessage: (message: ReceivedMessage) => ReactNode;
  trailingContent?: ReactNode;
  className?: string;
}

/**
 * The Conversation UI: the call's transcript and message box, in a pane on the right of the Call
 * UI (like a meeting's chat). On a narrow screen it covers the call instead. Always mounted, so
 * the transcript keeps its place; closed, it is collapsed and inert.
 */
export function ConversationPane({
  id,
  open,
  onClose,
  agentState,
  messages,
  renderAfterMessage,
  trailingContent,
  className,
}: ConversationPaneProps) {
  return (
    <aside
      id={id}
      aria-label="Conversation"
      data-open={open || undefined}
      inert={!open}
      className={cn(
        'bg-background z-40 overflow-hidden',
        // Narrow: covers the call, sliding in from the right.
        'invisible absolute inset-0 translate-x-full transition-[translate,visibility] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]',
        'data-[open]:visible data-[open]:translate-x-0',
        // Wide: a column beside the call that opens to 400px.
        '@4xl/call-root:relative @4xl/call-root:inset-auto @4xl/call-root:w-0 @4xl/call-root:translate-x-0 @4xl/call-root:border-l @4xl/call-root:transition-[width,visibility] @4xl/call-root:data-[open]:w-[400px]',
        'motion-reduce:transition-none',
        className
      )}
    >
      <div className="flex h-full w-full flex-col @4xl/call-root:w-[400px]">
        <header className="flex h-14 shrink-0 items-center justify-between border-b pr-2 pl-5">
          <h2 className="font-display text-base font-semibold">Conversation</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close conversation"
            className="text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring/60 rounded-full p-2 transition-colors outline-none focus-visible:ring-[3px]"
          >
            <XIcon aria-hidden="true" className="size-4" />
          </button>
        </header>
        <AgentChatTranscript
          agentState={agentState}
          messages={messages}
          renderAfterMessage={renderAfterMessage}
          trailingContent={trailingContent}
          className="min-h-0 flex-1 **:data-[slot=message-scroller-content]:p-4"
        />
        <div className="shrink-0 border-t p-3">
          <ChatComposer focusWhen={open} onEscape={onClose} />
        </div>
      </div>
    </aside>
  );
}
