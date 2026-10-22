import type { ConfirmState, TelcoCard } from '@/lib/telco-topics';

export type OverlayItem =
  | { kind: 'card'; key: string; card: TelcoCard }
  | { kind: 'confirm'; key: string; confirm: ConfirmState };

export const cardKey = (card: TelcoCard) => `card-${card.id}`;
export const confirmKey = (confirm: ConfirmState) => `confirm-${confirm.action_id}`;

/**
 * What the call overlay shows: one thing at a time. A confirm card waiting for its code always
 * wins (the caller has to act on it, so it can't be dismissed). Otherwise it is whichever came
 * last -- the latest package or case card, or the settled confirm card -- unless dismissed;
 * nothing older comes back after a dismissal.
 */
export function orderOverlayItems(
  cards: TelcoCard[],
  confirm: ConfirmState | null,
  dismissed: ReadonlySet<string>
): OverlayItem[] {
  if (confirm?.state === 'awaiting_code') {
    return [{ kind: 'confirm', key: confirmKey(confirm), confirm }];
  }
  const latest = cards.at(-1);
  const confirmIsNewest = confirm && (!latest || confirm.revealedAt >= latest.revealedAt);
  if (confirmIsNewest) {
    return dismissed.has(confirmKey(confirm))
      ? []
      : [{ kind: 'confirm', key: confirmKey(confirm), confirm }];
  }
  if (latest && !dismissed.has(cardKey(latest))) {
    return [{ kind: 'card', key: cardKey(latest), card: latest }];
  }
  return [];
}
