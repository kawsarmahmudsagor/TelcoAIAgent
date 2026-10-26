'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowLeftIcon, Loader2Icon, SquarePenIcon } from 'lucide-react';
import { useChatBubble } from '@/components/chat-bubble/chat-bubble-context';
import { useAssistant } from '@/components/portal/assistant/assistant-provider';
import { listVisitorConversations } from '@/lib/public-conversations';
import { cn } from '@/lib/shadcn/utils';
import type { VisitorConversationSummary } from '@/lib/types';

const PAGE_SIZE = 20;
const startedFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

/**
 * This browser's earlier chats (and, logged in, the customer's own from any browser), newest
 * first. Picking one carries it on; "New chat" clears the panel. Shown in place of the transcript
 * while the header's history toggle is on.
 */
export function ConversationHistory({ compact }: { compact: boolean }) {
  const { visitorId } = useChatBubble();
  const { resumedId, openConversation, newChat, setHistoryOpen } = useAssistant();
  const [items, setItems] = useState<VisitorConversationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);

  const load = useCallback(
    async (offset: number, signal?: AbortSignal) => {
      if (!visitorId) return;
      setLoading(true);
      setFailed(false);
      try {
        const page = await listVisitorConversations(
          visitorId,
          { limit: PAGE_SIZE, offset },
          signal
        );
        setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
        setTotal(page.total);
      } catch (error) {
        if (signal?.aborted) return;
        console.error('Failed to load the chat history:', error);
        setFailed(true);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [visitorId]
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(0, controller.signal);
    return () => controller.abort();
  }, [load]);

  const pick = async (id: string) => {
    setOpening(id);
    await openConversation(id);
    setOpening(null);
  };

  const linkButton =
    'text-brand font-bold underline-offset-2 outline-none hover:underline focus-visible:underline';

  return (
    <div className={cn('flex h-full flex-col gap-3 overflow-y-auto', compact ? 'p-4' : 'p-5')}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setHistoryOpen(false)}
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring/60 inline-flex min-h-9 items-center gap-1.5 rounded-[10px] px-2 text-xs font-bold outline-none focus-visible:ring-[3px] [&_svg]:size-4"
        >
          <ArrowLeftIcon aria-hidden="true" />
          Back
        </button>
        <h3 className="flex-1 text-[13px] font-bold">Your chats</h3>
        <button
          type="button"
          onClick={newChat}
          className="border-line bg-surface hover:border-mint focus-visible:ring-ring/60 inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-xs font-bold outline-none focus-visible:ring-[3px] motion-safe:transition-colors [&_svg]:size-3.5"
        >
          <SquarePenIcon aria-hidden="true" />
          New chat
        </button>
      </div>
      {items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((item) => {
            const current = item.id === resumedId;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => void pick(item.id)}
                  disabled={opening !== null}
                  aria-current={current ? 'true' : undefined}
                  className={cn(
                    'bg-surface border-line hover:border-brand focus-visible:ring-ring/60 flex w-full flex-col gap-1 rounded-[12px] border px-3.5 py-3 text-left outline-none focus-visible:ring-[3px] disabled:opacity-70 motion-safe:transition-colors',
                    current && 'border-brand'
                  )}
                >
                  <span className="line-clamp-2 text-[13px] leading-[1.5]">
                    {item.preview || 'Voice chat'}
                  </span>
                  <span className="text-muted-foreground flex items-center gap-1.5 text-[10px]">
                    {startedFormat.format(new Date(item.started_at))} · {item.message_count}{' '}
                    {item.message_count === 1 ? 'message' : 'messages'}
                    {current && <span className="text-brand font-semibold">· Open now</span>}
                    {opening === item.id && (
                      <Loader2Icon className="size-3 animate-spin" aria-hidden="true" />
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <div role="status" className="text-muted-foreground text-center text-xs">
        {loading ? (
          <Loader2Icon className="text-brand mx-auto size-5 animate-spin" aria-label="Loading" />
        ) : failed ? (
          <button type="button" onClick={() => void load(items.length)} className={linkButton}>
            Couldn’t load your chats. Try again
          </button>
        ) : items.length === 0 ? (
          'No earlier chats yet.'
        ) : items.length < total ? (
          <button type="button" onClick={() => void load(items.length)} className={linkButton}>
            Show more
          </button>
        ) : null}
      </div>
    </div>
  );
}
