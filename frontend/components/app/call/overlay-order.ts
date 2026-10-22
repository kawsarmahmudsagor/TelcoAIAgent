import type { BookingFormEntry, ShortlistResult } from '@/lib/livekit-text-streams';

export type OverlayItem =
  | { kind: 'shortlist'; key: string; result: ShortlistResult }
  | { kind: 'form'; key: string; entry: BookingFormEntry; hidden: boolean };

/** form_id -> the revision the caller dismissed the form at. */
export type FormDismissals = ReadonlyMap<string, number>;

/**
 * Whether a booking form is off screen. A dismissed form comes back when the agent changes it
 * and it still needs the caller (collecting or review).
 */
export function isFormHidden(entry: BookingFormEntry, dismissals: FormDismissals): boolean {
  const dismissedAt = dismissals.get(entry.form.form_id);
  if (dismissedAt === undefined) return false;
  const { revision, state } = entry.form;
  return !(revision > dismissedAt && (state === 'collecting' || state === 'review'));
}

/**
 * What the call overlay shows: one thing at a time, whichever appeared or changed last -- the
 * latest search result (or single listing), or a booking form. Opening the form takes the cards
 * away; a newer search hides the form until the agent changes it again. When the newest thing is
 * dismissed (or a booked form steps aside), nothing older comes back. Forms not on screen stay in
 * the list, flagged hidden, so their typed input survives.
 */
export function orderOverlayItems(
  results: ShortlistResult[],
  forms: BookingFormEntry[],
  formDismissals: FormDismissals,
  dismissedResultIds: ReadonlySet<number>
): OverlayItem[] {
  const latest = results.at(-1);
  const newestForm = forms.reduce<BookingFormEntry | undefined>(
    (newest, entry) => (!newest || entry.updatedAt >= newest.updatedAt ? entry : newest),
    undefined
  );
  const formOnTop =
    newestForm !== undefined && (!latest || newestForm.updatedAt > latest.revealedAt);

  const formItems: OverlayItem[] = forms.map((entry) => ({
    kind: 'form',
    key: `f-${entry.form.form_id}`,
    entry,
    hidden: !formOnTop || entry !== newestForm || isFormHidden(entry, formDismissals),
  }));
  const shortlistItems: OverlayItem[] =
    !formOnTop && latest && !dismissedResultIds.has(latest.id)
      ? [{ kind: 'shortlist', key: `s-${latest.id}`, result: latest }]
      : [];
  return [...shortlistItems, ...formItems];
}
