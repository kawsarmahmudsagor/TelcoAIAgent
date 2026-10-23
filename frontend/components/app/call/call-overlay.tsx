'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { XIcon } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { CaseCard } from '@/components/portal/assistant/cards/case-card';
import { ConfirmCard } from '@/components/portal/assistant/cards/confirm-card';
import { PackageCards } from '@/components/portal/assistant/cards/package-cards';
import { cn } from '@/lib/shadcn/utils';
import type { ConfirmState, TelcoCard, TelcoPackage } from '@/lib/telco-topics';
import { confirmKey, orderOverlayItems } from './overlay-order';

// A settled confirm card has nothing left to do; it steps aside after a moment.
const SETTLED_HIDE_MS = 6000;

const ITEM_SHELL =
  'relative shrink-0 rounded-2xl bg-background/75 p-3 shadow-2xl shadow-black/40 backdrop-blur-xl';

interface CallOverlayProps {
  cards: TelcoCard[];
  confirm: ConfirmState | null;
  /** A package card's Buy: asks the agent in the chat. */
  onBuy(pkg: TelcoPackage): void;
  /** Whether anything is on screen, e.g. so the stage can make room for the side column. */
  onVisibleChange?: (visible: boolean) => void;
  className?: string;
}

/**
 * The agent's latest card over the call: a column on the left of a wide screen, a sheet along
 * the bottom of a narrow one. A confirm card waiting for its code stays until it is settled.
 * The text-stream hooks live in the call view (one handler per topic), so this only renders what
 * it's given. Dismissing here only hides a card from the call; the conversation keeps it.
 */
export function CallOverlay({
  cards,
  confirm,
  onBuy,
  onVisibleChange,
  className,
}: CallOverlayProps) {
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  const dismiss = (key: string) => setDismissed((prev) => new Set(prev).add(key));

  // Hide each confirm card a few seconds after it settles.
  const timersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  useEffect(() => {
    if (!confirm || confirm.state === 'awaiting_code') return;
    const key = confirmKey(confirm);
    if (timersRef.current.has(key)) return;
    timersRef.current.set(
      key,
      setTimeout(() => setDismissed((prev) => new Set(prev).add(key)), SETTLED_HIDE_MS)
    );
  }, [confirm]);
  useEffect(() => {
    const timers = timersRef.current;
    return () => timers.forEach(clearTimeout);
  }, []);

  const items = useMemo(
    () => orderOverlayItems(cards, confirm, dismissed),
    [cards, confirm, dismissed]
  );
  const visible = items.length > 0;
  const confirmActive = items.some(
    (item) => item.kind === 'confirm' && item.confirm.state === 'awaiting_code'
  );

  useEffect(() => onVisibleChange?.(visible), [visible, onVisibleChange]);

  return (
    <aside
      aria-label="The agent’s cards"
      data-form-active={confirmActive || undefined}
      inert={!visible}
      className={cn(
        'absolute z-20 flex flex-col gap-3 overflow-y-auto overscroll-contain p-1',
        // Narrow: a sheet along the bottom of the stage.
        'inset-x-3 top-auto bottom-2 max-h-[62%] data-[form-active]:max-h-[94%]',
        // Wide: a column on the left, clear of the page's corner logo.
        '@5xl:inset-x-auto @5xl:top-16 @5xl:bottom-auto @5xl:left-6 @5xl:max-h-[calc(100%-5rem)] @5xl:w-[420px]',
        'transition-[opacity,translate] duration-300 ease-out motion-reduce:transition-opacity',
        visible
          ? 'translate-0 opacity-100'
          : 'pointer-events-none translate-y-4 opacity-0 @5xl:-translate-x-4 @5xl:translate-y-0',
        className
      )}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        {items.map((item) => (
          <motion.div
            key={item.key}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.35, delay: 0.15 } }}
            exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.3, ease: 'easeIn' } }}
            className={ITEM_SHELL}
          >
            {/* No dismiss while the agent waits on the code: hiding it wouldn't cancel it. */}
            {!(item.kind === 'confirm' && item.confirm.state === 'awaiting_code') && (
              <button
                type="button"
                onClick={() => dismiss(item.key)}
                aria-label="Hide card"
                className="text-muted-foreground hover:bg-muted hover:text-foreground absolute top-1.5 right-2 z-10 rounded-full p-1 transition-colors"
              >
                <XIcon aria-hidden="true" className="size-3.5" />
              </button>
            )}
            {item.kind === 'confirm' ? (
              <ConfirmCard key={item.confirm.action_id} confirm={item.confirm} />
            ) : item.card.kind === 'packages' ? (
              <PackageCards data={item.card.data} onBuy={onBuy} />
            ) : (
              <CaseCard data={item.card.data} />
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </aside>
  );
}
