'use client';

import { useEffect, useRef, useState } from 'react';
import { type Room, RoomEvent, type TextStreamReader } from 'livekit-client';
import { toast } from 'sonner';
import type { AgentState, ReceivedMessage } from '@livekit/components-react';
import { showSmsToast } from '@/components/portal/actions/sms-toast';
import { invalidatePortal } from '@/lib/portal-sync';
import type { PackageView, PortalActionKind } from '@/lib/types/portal';

// Must match backend/app/agent/topics.py.
export const TELCO_TOPICS = {
  accountChanged: 'telco.account_changed',
  otpSms: 'telco.otp_sms',
  confirm: 'telco.confirm',
  packages: 'telco.packages',
  caseCreated: 'telco.case_created',
} as const;
export const TELCO_RPC = {
  confirm: 'telco.confirm_action',
  cancel: 'telco.cancel_action',
} as const;

/** `telco.otp_sms`: the demo SMS with the code. */
export interface TelcoOtpSms {
  action_id: string;
  code: string;
  to: string;
  expires_at: string;
}

export type ConfirmCardState = 'awaiting_code' | 'done' | 'cancelled' | 'expired';

/** `telco.confirm`: the agent's pending purchase, recharge or redemption, at its latest state. */
export interface ConfirmState {
  action_id: string;
  kind: PortalActionKind;
  state: ConfirmCardState;
  title: string;
  /** Taka; null for a redemption (paid in points). */
  amount: number | null;
  /** `balance` | `bkash` | `nagad` | `card`, or `points` for a redemption. */
  pay_from: string;
  /** A redemption's points cost. */
  points?: number;
  /** A recharge's target number. */
  target?: string;
  expires_at: string;
  /** The transaction ref, once done. */
  ref?: string | null;
  /** Epoch ms the card first appeared: pins it to its turn in the transcript. */
  revealedAt: number;
}

/** One `telco.packages` item: the same fields as the portal's package list. */
export type TelcoPackage = PackageView;

export interface TelcoPackagesPayload {
  title: string;
  packages: TelcoPackage[];
}

/** `telco.case_created`. */
export interface TelcoCasePayload {
  ref: string;
  category: string;
  priority: string;
  status: string;
  created_at: string;
}

export type TelcoCard =
  | { id: number; kind: 'packages'; revealedAt: number; data: TelcoPackagesPayload }
  | { id: number; kind: 'case'; revealedAt: number; data: TelcoCasePayload };

type HeldCard =
  | { kind: 'packages'; data: TelcoPackagesPayload }
  | { kind: 'case'; data: TelcoCasePayload };

export interface TelcoTopics {
  /** Package and case cards shown this session, oldest first. */
  cards: TelcoCard[];
  /** The agent's latest confirm card, or null. */
  confirm: ConfirmState | null;
}

// A card is sent the moment the tool runs, before the agent has said a word about it. It is held
// until the agent next *starts* speaking (the reply presenting it); speech already playing when
// it arrived doesn't count. The timer is only a safety net (a reply that was never spoken).
const FALLBACK_REVEAL_MS = 60_000;

function readJson<T>(reader: TextStreamReader, topic: string, use: (payload: T) => void) {
  reader
    .readAll()
    .then((text) => use(JSON.parse(text) as T))
    .catch((err) => console.error(`Failed to read ${topic}:`, err));
}

/**
 * The telco agent's cards and live-sync topics for one room. Mount it exactly once per room:
 * livekit-client allows one handler per topic.
 *
 * - `telco.otp_sms` shows the SMS toast; `telco.account_changed` refetches the portal's data.
 * - `telco.confirm` upserts the confirm card by `action_id` (the latest state wins).
 * - `telco.packages` and `telco.case_created` add cards, held until the agent speaks about them.
 *
 * Everything resets when the room disconnects.
 */
export function useTelcoTopics(room: Room | undefined, agentState: AgentState): TelcoTopics {
  const [cards, setCards] = useState<TelcoCard[]>([]);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const nextIdRef = useRef(0);
  const heldRef = useRef<HeldCard[]>([]);
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The SMS toast per action, dismissed once its card is settled.
  const smsToastsRef = useRef(new Map<string, string | number>());

  const clearTimer = () => {
    if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
    fallbackTimerRef.current = null;
  };

  const revealHeld = () => {
    clearTimer();
    const due = heldRef.current;
    heldRef.current = [];
    if (due.length === 0) return;
    const now = Date.now();
    setCards((prev) => [
      ...prev,
      ...due.map((card) => ({ ...card, id: ++nextIdRef.current, revealedAt: now }) as TelcoCard),
    ]);
  };

  const hold = (card: HeldCard) => {
    heldRef.current.push(card);
    clearTimer();
    fallbackTimerRef.current = setTimeout(revealHeld, FALLBACK_REVEAL_MS);
  };

  useEffect(() => {
    if (!room) return;
    const smsToasts = smsToastsRef.current;

    const reset = () => {
      clearTimer();
      heldRef.current = [];
      for (const id of smsToasts.values()) toast.dismiss(id);
      smsToasts.clear();
      setCards([]);
      setConfirm(null);
    };

    const onSms = (reader: TextStreamReader) =>
      readJson<TelcoOtpSms>(reader, TELCO_TOPICS.otpSms, (sms) => {
        const id = showSmsToast({ code: sms.code, to: sms.to, expiresAt: sms.expires_at });
        smsToasts.set(sms.action_id, id);
      });

    const onConfirm = (reader: TextStreamReader) =>
      readJson<Omit<ConfirmState, 'revealedAt'>>(reader, TELCO_TOPICS.confirm, (card) => {
        setConfirm((prev) =>
          prev?.action_id === card.action_id
            ? { ...prev, ...card }
            : { ...card, revealedAt: Date.now() }
        );
      });

    const onPackages = (reader: TextStreamReader) =>
      readJson<TelcoPackagesPayload>(reader, TELCO_TOPICS.packages, (data) => {
        if (data.packages?.length) hold({ kind: 'packages', data });
      });

    const onCase = (reader: TextStreamReader) =>
      readJson<TelcoCasePayload>(reader, TELCO_TOPICS.caseCreated, (data) =>
        hold({ kind: 'case', data })
      );

    const onAccountChanged = (reader: TextStreamReader) =>
      readJson<{ kind: string; ref: string }>(reader, TELCO_TOPICS.accountChanged, () =>
        invalidatePortal()
      );

    room.registerTextStreamHandler(TELCO_TOPICS.otpSms, onSms);
    room.registerTextStreamHandler(TELCO_TOPICS.confirm, onConfirm);
    room.registerTextStreamHandler(TELCO_TOPICS.packages, onPackages);
    room.registerTextStreamHandler(TELCO_TOPICS.caseCreated, onCase);
    room.registerTextStreamHandler(TELCO_TOPICS.accountChanged, onAccountChanged);
    room.on(RoomEvent.Disconnected, reset);
    return () => {
      for (const topic of Object.values(TELCO_TOPICS)) room.unregisterTextStreamHandler(topic);
      room.off(RoomEvent.Disconnected, reset);
      reset();
    };
    // hold/revealHeld only use refs and the stable setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room]);

  // A settled card's SMS has served its purpose.
  useEffect(() => {
    if (!confirm || confirm.state === 'awaiting_code') return;
    const id = smsToastsRef.current.get(confirm.action_id);
    if (id === undefined) return;
    smsToastsRef.current.delete(confirm.action_id);
    toast.dismiss(id);
  }, [confirm]);

  const prevStateRef = useRef(agentState);
  useEffect(() => {
    const prev = prevStateRef.current;
    prevStateRef.current = agentState;
    const startedSpeaking = agentState === 'speaking' && prev !== 'speaking';
    // The reply was dropped: no speaking transition is coming.
    const gaveUp = agentState === 'listening' && prev === 'thinking';
    if ((startedSpeaking || gaveUp) && heldRef.current.length > 0) revealHeld();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentState]);

  useEffect(() => clearTimer, []);

  return { cards, confirm };
}

/**
 * Pins each card to the turn it arrived in: after the last message of that turn (the agent's
 * reply), i.e. just before the user's next message. The turn is the latest user message sent
 * before the card was revealed. Cards with no message to sit under yet are `unplaced`.
 */
export function placeAfterTurn<T extends { revealedAt: number }>(
  messages: ReceivedMessage[],
  items: T[]
): { byMessageId: Map<string, T[]>; unplaced: T[] } {
  const byMessageId = new Map<string, T[]>();
  const unplaced: T[] = [];

  for (const item of items) {
    let turnStart = -1;
    messages.forEach((m, i) => {
      if (m.from?.isLocal && m.timestamp <= item.revealedAt) turnStart = i;
    });
    const nextUser = messages.findIndex((m, i) => i > turnStart && m.from?.isLocal);
    const turnEnd = nextUser === -1 ? messages.length - 1 : nextUser - 1;

    if (turnEnd < 0) {
      unplaced.push(item);
      continue;
    }
    const anchorId = messages[turnEnd].id;
    byMessageId.set(anchorId, [...(byMessageId.get(anchorId) ?? []), item]);
  }

  return { byMessageId, unplaced };
}
