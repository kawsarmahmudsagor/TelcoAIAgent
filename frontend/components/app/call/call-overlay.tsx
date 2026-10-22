'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { XIcon } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { ApartmentShortlist } from '@/components/app/apartment-shortlist';
import { BookingFormCard } from '@/components/app/booking-form-card';
import type { BookingFormEntry, ShortlistResult } from '@/lib/livekit-text-streams';
import { cn } from '@/lib/shadcn/utils';
import { orderOverlayItems } from './overlay-order';

// A booked form has nothing left to do; it steps aside after a moment.
const BOOKED_HIDE_MS = 6000;

const ITEM_SHELL =
  'relative shrink-0 rounded-2xl bg-background/75 shadow-2xl shadow-black/40 backdrop-blur-xl [&_[data-slot=bubble-content]]:w-full [&_[data-slot=bubble]]:w-full';

interface CallOverlayProps {
  results: ShortlistResult[];
  forms: BookingFormEntry[];
  /** Whether anything is on screen, e.g. so the stage can make room for the side column. */
  onVisibleChange?: (visible: boolean) => void;
  className?: string;
}

/**
 * The latest search result and any booking form, over the call: a column on the left of a wide
 * screen, a sheet along the bottom of a narrow one. A new search fades the previous one out. The
 * text-stream hooks live in the call view (one handler per topic), so this only renders what it's
 * given. Dismissing here only hides a result from the call; the conversation keeps it. A
 * dismissed booking form is only hidden, so a half-typed name or number isn't lost.
 */
export function CallOverlay({ results, forms, onVisibleChange, className }: CallOverlayProps) {
  const [formDismissals, setFormDismissals] = useState<ReadonlyMap<string, number>>(
    () => new Map()
  );
  const [dismissedResultIds, setDismissedResultIds] = useState<ReadonlySet<number>>(
    () => new Set()
  );
  const dismissForm = (formId: string, revision: number) =>
    setFormDismissals((prev) => new Map(prev).set(formId, revision));

  // Hide each form a few seconds after it's booked.
  const bookedTimersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  useEffect(() => {
    const timers = bookedTimersRef.current;
    for (const { form } of forms) {
      if (form.state !== 'booked' || timers.has(form.form_id)) continue;
      timers.set(
        form.form_id,
        setTimeout(
          () => setFormDismissals((prev) => new Map(prev).set(form.form_id, form.revision)),
          BOOKED_HIDE_MS
        )
      );
    }
  }, [forms]);
  useEffect(() => {
    const timers = bookedTimersRef.current;
    return () => timers.forEach(clearTimeout);
  }, []);

  const items = useMemo(
    () => orderOverlayItems(results, forms, formDismissals, dismissedResultIds),
    [results, forms, formDismissals, dismissedResultIds]
  );
  const visible = items.some((item) => item.kind === 'shortlist' || !item.hidden);
  const formActive = items.some(
    (item) => item.kind === 'form' && !item.hidden && item.entry.form.state !== 'booked'
  );

  useEffect(() => onVisibleChange?.(visible), [visible, onVisibleChange]);

  return (
    <aside
      aria-label="Listings and bookings"
      data-form-active={formActive || undefined}
      inert={!visible}
      className={cn(
        'absolute z-20 flex flex-col gap-3 overflow-y-auto overscroll-contain p-1',
        // Narrow: a sheet along the bottom of the stage.
        'inset-x-3 top-auto bottom-2 max-h-[62%] data-[form-active]:max-h-[94%]',
        // Wide: a column on the left, clear of the page's corner logo.
        '@5xl:inset-x-auto @5xl:top-16 @5xl:bottom-auto @5xl:left-6 @5xl:max-h-[calc(100%-5rem)] @5xl:w-[420px] @5xl:data-[form-active]:max-h-[calc(100%-5rem)]',
        'transition-[opacity,translate] duration-300 ease-out motion-reduce:transition-opacity',
        visible
          ? 'translate-0 opacity-100'
          : 'pointer-events-none translate-y-4 opacity-0 @5xl:-translate-x-4 @5xl:translate-y-0',
        className
      )}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        {items.map((item) =>
          item.kind === 'shortlist' ? (
            <motion.div
              key={item.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.35, delay: 0.15 } }}
              exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.3, ease: 'easeIn' } }}
              className={ITEM_SHELL}
            >
              <ApartmentShortlist
                result={item.result}
                onDismiss={(id) => setDismissedResultIds((prev) => new Set(prev).add(id))}
                listClassName="max-h-none overflow-y-visible overscroll-auto"
              />
            </motion.div>
          ) : (
            <div key={item.key} className={cn(ITEM_SHELL, item.hidden && 'hidden')}>
              {/* No dismiss while the agent waits on a yes: hiding it wouldn't stop the booking. */}
              {item.entry.form.state !== 'review' && (
                <button
                  type="button"
                  onClick={() => dismissForm(item.entry.form.form_id, item.entry.form.revision)}
                  aria-label="Hide booking form"
                  className="text-muted-foreground hover:bg-muted hover:text-foreground absolute top-1.5 right-2 z-10 rounded-full p-1 transition-colors"
                >
                  <XIcon aria-hidden="true" className="size-3.5" />
                </button>
              )}
              <BookingFormCard form={item.entry.form} />
            </div>
          )
        )}
      </AnimatePresence>
    </aside>
  );
}
