'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeftIcon, HistoryIcon, Loader2Icon, MessageSquareIcon } from 'lucide-react';
import { Popover as PopoverPrimitive } from 'radix-ui';
import { Streamdown } from 'streamdown';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import { Button } from '@/components/ui/button';
import { Message, MessageContent } from '@/components/ui/message';
import { formatDateTime, formatRelative } from '@/lib/format';
import { getVisitorConversation, listVisitorConversations } from '@/lib/public-conversations';
import { cn } from '@/lib/shadcn/utils';
import type { VisitorConversationDetail, VisitorConversationSummary } from '@/lib/types';

// The 3 most recent load first; the rest come in pages as the list is scrolled.
const FIRST_PAGE = 3;
const NEXT_PAGE = 5;

function conversationTitle(preview: string | null) {
  return preview?.trim() || 'Conversation';
}

/**
 * The header's "recent conversations" button and its dropdown: this browser's earlier chats,
 * newest first. The session in progress (`currentRoom`) is left out; while connected a "Current
 * conversation" row leads back to it.
 */
export function ConversationHistoryMenu({
  visitorId,
  currentRoom,
  isConnected,
  open,
  onOpenChange,
  onSelect,
  onShowCurrent,
}: {
  visitorId: string;
  currentRoom: string | undefined;
  isConnected: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (conversation: VisitorConversationSummary) => void;
  onShowCurrent: () => void;
}) {
  return (
    <PopoverPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <PopoverPrimitive.Trigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Recent conversations"
          title="Recent conversations"
        >
          <HistoryIcon aria-hidden="true" />
        </Button>
      </PopoverPrimitive.Trigger>
      {/* No portal: the content stays inside the panel, so it keeps the panel's scoped tokens. */}
      <PopoverPrimitive.Content
        align="end"
        sideOffset={6}
        collisionPadding={8}
        // Radix closes the dropdown on Escape; keep the key from also closing the panel.
        onKeyDown={(event) => {
          if (event.key === 'Escape') event.stopPropagation();
        }}
        className="bg-popover text-popover-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95 z-20 w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-lg border shadow-lg"
      >
        <p className="text-muted-foreground border-b px-3 py-2 text-xs font-medium">
          Recent conversations
        </p>
        {isConnected && (
          <button
            type="button"
            onClick={onShowCurrent}
            className="hover:bg-muted/60 focus-visible:bg-muted/60 flex w-full items-center gap-2 border-b px-3 py-2 text-left text-sm outline-none"
          >
            <span aria-hidden="true" className="size-2 shrink-0 rounded-full bg-emerald-500" />
            <span className="flex-1 truncate font-medium">Current conversation</span>
            <span className="text-muted-foreground text-xs">Live</span>
          </button>
        )}
        <ConversationList visitorId={visitorId} currentRoom={currentRoom} onSelect={onSelect} />
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Root>
  );
}

type ListState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; items: VisitorConversationSummary[]; total: number };

/** Mounted while the dropdown is open, so every opening shows a fresh list. */
function ConversationList({
  visitorId,
  currentRoom,
  onSelect,
}: {
  visitorId: string;
  currentRoom: string | undefined;
  onSelect: (conversation: VisitorConversationSummary) => void;
}) {
  const [state, setState] = useState<ListState>({ status: 'loading' });
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingMoreRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    listVisitorConversations(
      visitorId,
      { limit: FIRST_PAGE, offset: 0, excludeRoom: currentRoom },
      controller.signal
    )
      .then((page) => setState({ status: 'ready', items: page.items, total: page.total }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.error('Failed to load recent conversations:', error);
          setState({ status: 'error' });
        }
      });
    return () => controller.abort();
  }, [visitorId, currentRoom, attempt]);

  const items = state.status === 'ready' ? state.items : [];
  const hasMore = state.status === 'ready' && state.items.length < state.total;

  const loadMore = useCallback(() => {
    if (state.status !== 'ready' || loadingMoreRef.current) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    listVisitorConversations(visitorId, {
      limit: NEXT_PAGE,
      offset: state.items.length,
      excludeRoom: currentRoom,
    })
      .then((page) =>
        setState((prev) => {
          if (prev.status !== 'ready') return prev;
          const seen = new Set(prev.items.map((item) => item.id));
          const fresh = page.items.filter((item) => !seen.has(item.id));
          // Nothing new means the list shifted under us: stop asking.
          const total = fresh.length === 0 ? prev.items.length : page.total;
          return { status: 'ready', items: [...prev.items, ...fresh], total };
        })
      )
      .catch((error: unknown) => console.error('Failed to load more conversations:', error))
      .finally(() => {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      });
  }, [state, visitorId, currentRoom]);

  // The "loading more" row sits just below the first rows, so it only shows (and loads the next
  // page) once the list is scrolled to it.
  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!hasMore || !root || !sentinel) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry && entry.intersectionRatio >= 0.5) loadMore();
      },
      { root, threshold: 0.5 }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  if (state.status === 'loading') {
    return (
      <div className="text-muted-foreground flex h-15 items-center justify-center gap-2 text-xs">
        <Loader2Icon aria-hidden="true" className="size-3.5 animate-spin" />
        Loading…
      </div>
    );
  }
  if (state.status === 'error') {
    return (
      <div className="flex flex-col items-center gap-2 px-3 py-4 text-center text-xs">
        <p className="text-muted-foreground">Couldn’t load your conversations.</p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            setState({ status: 'loading' });
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </Button>
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <p className="text-muted-foreground px-3 py-4 text-center text-xs">
        No earlier conversations on this device yet.
      </p>
    );
  }

  return (
    // Exactly three rows tall: the rest scroll into view (and load) below them.
    <div ref={scrollRef} className="max-h-45 overflow-y-auto overscroll-contain">
      <ul aria-label="Earlier conversations" aria-busy={loadingMore}>
        {items.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              onClick={() => onSelect(conversation)}
              className="hover:bg-muted/60 focus-visible:bg-muted/60 flex h-15 w-full items-center gap-2.5 px-3 text-left outline-none"
            >
              <MessageSquareIcon
                aria-hidden="true"
                className="text-muted-foreground size-4 shrink-0"
              />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate text-sm font-medium">
                  {conversationTitle(conversation.preview)}
                </span>
                <span className="text-muted-foreground truncate text-xs">
                  <time
                    dateTime={conversation.started_at}
                    title={formatDateTime(conversation.started_at)}
                  >
                    {formatRelative(conversation.started_at)}
                  </time>
                  {' · '}
                  {conversation.message_count}{' '}
                  {conversation.message_count === 1 ? 'message' : 'messages'}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {hasMore && (
        <div
          ref={sentinelRef}
          className="text-muted-foreground flex h-15 items-center justify-center gap-2 text-xs"
        >
          <Loader2Icon aria-hidden="true" className="size-3.5 animate-spin" />
          Loading earlier conversations…
        </div>
      )}
    </div>
  );
}

type DetailState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; conversation: VisitorConversationDetail };

/**
 * One earlier conversation's transcript, read-only, over the panel's body. The live session
 * view stays mounted underneath; `onBack` returns to it.
 */
export function PastConversationView({
  visitorId,
  summary,
  onBack,
  className,
}: {
  visitorId: string;
  summary: VisitorConversationSummary;
  onBack: () => void;
  className?: string;
}) {
  const [state, setState] = useState<DetailState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const backRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    backRef.current?.focus();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    getVisitorConversation(visitorId, summary.id, controller.signal)
      .then((conversation) => setState({ status: 'ready', conversation }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.error('Failed to load the conversation:', error);
          setState({ status: 'error' });
        }
      });
    return () => controller.abort();
  }, [visitorId, summary.id, attempt]);

  const messages =
    state.status === 'ready'
      ? state.conversation.messages.filter((message) => message.text?.trim())
      : [];

  return (
    <section
      aria-label="Earlier conversation"
      className={cn('bg-background flex flex-col', className)}
    >
      <div className="flex shrink-0 items-center gap-2 border-b px-2 py-1.5">
        <Button
          ref={backRef}
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="gap-1.5"
        >
          <ArrowLeftIcon aria-hidden="true" />
          Back to chat
        </Button>
        <span className="text-muted-foreground ml-auto truncate pr-2 text-xs">
          {formatDateTime(summary.started_at)}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4">
        {state.status === 'loading' && (
          <div className="text-muted-foreground flex items-center justify-center gap-2 py-8 text-xs">
            <Loader2Icon aria-hidden="true" className="size-3.5 animate-spin" />
            Loading conversation…
          </div>
        )}
        {state.status === 'error' && (
          <div className="flex flex-col items-center gap-2 py-8 text-center text-xs">
            <p className="text-muted-foreground">Couldn’t load this conversation.</p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setState({ status: 'loading' });
                setAttempt((n) => n + 1);
              }}
            >
              Try again
            </Button>
          </div>
        )}
        {state.status === 'ready' && messages.length === 0 && (
          <p className="text-muted-foreground py-8 text-center text-xs">
            This conversation has no messages.
          </p>
        )}
        {messages.length > 0 && (
          <ol className="flex flex-col gap-4" aria-label="Messages">
            {messages.map((message) => {
              const isUser = message.role === 'user';
              return (
                <li key={message.seq}>
                  <Message
                    align={isUser ? 'end' : 'start'}
                    title={formatDateTime(message.created_at)}
                  >
                    <MessageContent>
                      <Bubble
                        align={isUser ? 'end' : 'start'}
                        variant={isUser ? 'secondary' : 'ghost'}
                      >
                        <BubbleContent>
                          <Streamdown>{message.text ?? ''}</Streamdown>
                        </BubbleContent>
                      </Bubble>
                    </MessageContent>
                  </Message>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <p className="text-muted-foreground shrink-0 border-t px-4 py-2 text-center text-xs">
        This is an earlier conversation; it can’t be continued here.
      </p>
    </section>
  );
}
