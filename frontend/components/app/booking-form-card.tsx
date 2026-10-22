'use client';

import { type FormEvent, useId, useRef, useState } from 'react';
import { CalendarCheckIcon, CalendarDaysIcon, HomeIcon, Loader2Icon } from 'lucide-react';
import { motion } from 'motion/react';
import { useAgent, useMaybeRoomContext } from '@livekit/components-react';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Message, MessageContent } from '@/components/ui/message';
import type { BookingFormData } from '@/lib/livekit-text-streams';

// Must match RPC_SUBMIT / RPC_EDIT / RPC_CONFIRM in backend/app/agent/booking.py.
const RPC_SUBMIT = 'booking.submit';
const RPC_EDIT = 'booking.edit';
const RPC_CONFIRM = 'booking.confirm';

type Errors = Record<string, string>;

interface RpcReply {
  ok: boolean;
  errors?: Errors;
}

const UNREACHABLE = 'Could not reach the assistant. Please try again.';

function formatViewingTime(iso: string | null): string {
  if (!iso) return 'Time not set yet';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

interface BookingFormCardProps {
  form: BookingFormData;
}

/**
 * The viewing booking form in the chat. The agent fills it as the customer
 * talks; the customer can type their name and phone too. Submit sends them to
 * the agent, which reads everything back; Confirm books it.
 */
export function BookingFormCard({ form }: BookingFormCardProps) {
  const room = useMaybeRoomContext();
  const agent = useAgent();
  const nameId = useId();
  const phoneId = useId();

  const [fullName, setFullName] = useState(form.full_name ?? '');
  const [phone, setPhone] = useState(form.phone ?? '');
  const [rpcErrors, setRpcErrors] = useState<Errors | null>(null);
  const [busy, setBusy] = useState(false);
  // Take the agent's values whenever they change (e.g. said aloud), keeping
  // what the customer typed otherwise.
  const serverValues = `${form.full_name ?? ''}\u0000${form.phone ?? ''}`;
  const [syncedValues, setSyncedValues] = useState(serverValues);
  const [syncedRevision, setSyncedRevision] = useState(form.revision);
  if (syncedValues !== serverValues) {
    setSyncedValues(serverValues);
    setFullName(form.full_name ?? '');
    setPhone(form.phone ?? '');
  }
  if (syncedRevision !== form.revision) {
    setSyncedRevision(form.revision);
    setRpcErrors(null);
  }
  // booking.edit goes once per round of review: the revision it was sent for.
  const editSentForRef = useRef<number | null>(null);

  const errors = rpcErrors ?? form.errors ?? {};
  const locked = form.state === 'booking' || form.state === 'booked';
  const dirty = fullName !== (form.full_name ?? '') || phone !== (form.phone ?? '');
  const canConfirm = form.state === 'review' && !dirty;

  const call = async (method: string, payload: Record<string, unknown>): Promise<RpcReply> => {
    if (!room || !agent.identity) throw new Error('not connected');
    const reply = await room.localParticipant.performRpc({
      destinationIdentity: agent.identity,
      method,
      payload: JSON.stringify({ form_id: form.form_id, ...payload }),
    });
    return JSON.parse(reply) as RpcReply;
  };

  const onEdit = (field: 'full_name' | 'phone', value: string) => {
    if (field === 'full_name') setFullName(value);
    else setPhone(value);
    if (form.state === 'review' && editSentForRef.current !== form.revision) {
      // Back to collecting, so a spoken "yes" can't book the old values.
      editSentForRef.current = form.revision;
      call(RPC_EDIT, {}).catch((err) => console.error('booking.edit failed:', err));
    }
  };

  const send = async (method: string, payload: Record<string, unknown>) => {
    setBusy(true);
    setRpcErrors(null);
    try {
      const reply = await call(method, payload);
      if (!reply.ok) setRpcErrors(reply.errors ?? { form: UNREACHABLE });
    } catch (err) {
      console.error(`${method} failed:`, err);
      setRpcErrors({ form: UNREACHABLE });
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || locked) return;
    if (canConfirm) {
      void send(RPC_CONFIRM, {});
    } else {
      void send(RPC_SUBMIT, { full_name: fullName, phone });
    }
  };

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
              <div className="border-b px-3.5 py-2.5">
                <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
                  <CalendarDaysIcon className="size-3.5" />
                  Book a viewing
                </p>
              </div>

              <div className="flex flex-col gap-1.5 px-3.5 pt-3 text-sm">
                <p className="flex items-center gap-2">
                  <HomeIcon className="text-muted-foreground size-4 shrink-0" />
                  <span className={form.property_title ? '' : 'text-muted-foreground'}>
                    {form.property_title ?? 'Property not chosen yet'}
                  </span>
                </p>
                <p className="flex items-center gap-2">
                  <CalendarDaysIcon className="text-muted-foreground size-4 shrink-0" />
                  <span className={form.proposed_datetime ? '' : 'text-muted-foreground'}>
                    {formatViewingTime(form.proposed_datetime)}
                  </span>
                </p>
              </div>

              {form.state === 'booked' ? (
                <p
                  role="status"
                  className="m-3.5 flex items-center gap-2 rounded-xl bg-emerald-500/10 px-3 py-2.5 text-sm font-medium text-emerald-700 dark:text-emerald-400"
                >
                  <CalendarCheckIcon className="size-4 shrink-0" />
                  Viewing booked for {form.full_name}. We&apos;ll call you on {form.phone}.
                </p>
              ) : (
                <form onSubmit={onSubmit} className="flex flex-col gap-3 p-3.5" noValidate>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={nameId}>Name</Label>
                    <Input
                      id={nameId}
                      value={fullName}
                      autoComplete="name"
                      disabled={locked}
                      aria-invalid={Boolean(errors.full_name)}
                      onChange={(e) => onEdit('full_name', e.target.value)}
                    />
                    {errors.full_name && (
                      <p className="text-destructive text-xs">{errors.full_name}</p>
                    )}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={phoneId}>Mobile number</Label>
                    <Input
                      id={phoneId}
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel"
                      placeholder="01XXXXXXXXX"
                      value={phone}
                      disabled={locked}
                      aria-invalid={Boolean(errors.phone)}
                      onChange={(e) => onEdit('phone', e.target.value)}
                    />
                    {errors.phone && <p className="text-destructive text-xs">{errors.phone}</p>}
                  </div>
                  {(errors.form || errors.proposed_datetime) && (
                    <p role="alert" className="text-destructive text-xs">
                      {errors.form ?? errors.proposed_datetime}
                    </p>
                  )}
                  {canConfirm && (
                    <p className="text-muted-foreground text-xs">
                      Check the details, then confirm (or just say yes).
                    </p>
                  )}
                  <Button type="submit" disabled={busy || locked} className="w-full">
                    {(busy || form.state === 'booking') && <Loader2Icon className="animate-spin" />}
                    {form.state === 'booking'
                      ? 'Booking…'
                      : canConfirm
                        ? 'Confirm viewing'
                        : 'Submit details'}
                  </Button>
                </form>
              )}
            </motion.div>
          </BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  );
}
