'use client';

import { Building2Icon, XIcon } from 'lucide-react';
import { motion } from 'motion/react';
import type { ReceivedMessage } from '@livekit/components-react';
import { ApartmentCard } from '@/components/app/apartment-card';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import { Message, MessageContent } from '@/components/ui/message';
import type { ShortlistResult } from '@/lib/livekit-text-streams';
import { cn } from '@/lib/shadcn/utils';

// Rows are a fixed height (size-20 thumbnail + padding), so 5 of them is a
// known pixel height -- beyond that the list scrolls instead of pushing the
// rest of the chat transcript down.
const VISIBLE_COUNT = 5;

/**
 * Pins each search result (or booking form) to the turn it arrived in: after
 * the last message of that turn (the agent's reply), i.e. just before the
 * user's next message. The turn is the latest user message sent before the
 * result was revealed.
 *
 * Returns the results to show after each message id, plus any that have no
 * message to sit under yet (an empty transcript).
 */
export function placeShortlistResults<T extends { revealedAt: number }>(
  messages: ReceivedMessage[],
  results: T[]
): { byMessageId: Map<string, T[]>; unplaced: T[] } {
  const byMessageId = new Map<string, T[]>();
  const unplaced: T[] = [];

  for (const result of results) {
    let turnStart = -1;
    messages.forEach((m, i) => {
      if (m.from?.isLocal && m.timestamp <= result.revealedAt) turnStart = i;
    });
    const nextUser = messages.findIndex((m, i) => i > turnStart && m.from?.isLocal);
    const turnEnd = nextUser === -1 ? messages.length - 1 : nextUser - 1;

    if (turnEnd < 0) {
      unplaced.push(result);
      continue;
    }
    const anchorId = messages[turnEnd].id;
    byMessageId.set(anchorId, [...(byMessageId.get(anchorId) ?? []), result]);
  }

  return { byMessageId, unplaced };
}

interface ApartmentShortlistProps {
  result: ShortlistResult;
  onDismiss: (id: number) => void;
  /** Classes for the card list, e.g. to let an outer scrolling container hold a long list. */
  listClassName?: string;
}

export function ApartmentShortlist({ result, onDismiss, listClassName }: ApartmentShortlistProps) {
  const { cards } = result;

  return (
    <Message align="start">
      <MessageContent>
        <Bubble align="start" variant="ghost">
          <BubbleContent>
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="border-border bg-card/50 w-full overflow-hidden rounded-2xl border"
            >
              <div className="flex items-center justify-between gap-2 border-b px-3.5 py-2.5">
                <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
                  <Building2Icon className="size-3.5" />
                  {cards.length} {cards.length === 1 ? 'listing' : 'listings'} found
                </p>
                <button
                  type="button"
                  onClick={() => onDismiss(result.id)}
                  aria-label="Dismiss listings"
                  className="text-muted-foreground hover:bg-muted hover:text-foreground shrink-0 rounded-full p-1 transition-colors"
                >
                  <XIcon className="size-3.5" />
                </button>
              </div>
              <div
                className={cn(
                  'divide-border flex flex-col divide-y',
                  // Only a list that can scroll gets its own scroller: an idle overflow-y-auto with
                  // overscroll-contain would swallow wheel events meant for the transcript/overlay.
                  cards.length > VISIBLE_COUNT &&
                    'max-h-[520px] overflow-y-auto overscroll-contain',
                  listClassName
                )}
              >
                {cards.map((card, index) => (
                  <ApartmentCard key={card.id} card={card} index={index} />
                ))}
              </div>
            </motion.div>
          </BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  );
}
