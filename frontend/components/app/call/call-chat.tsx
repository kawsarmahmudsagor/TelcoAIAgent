'use client';

import { type KeyboardEvent, type Ref, useEffect, useRef, useState } from 'react';
import { CheckIcon, MessageCircleIcon, SendHorizontalIcon } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { toast } from 'sonner';
import { useChat } from '@livekit/components-react';
import { useGreetingDone } from '@/lib/livekit-text-streams';
import { cn } from '@/lib/shadcn/utils';

interface ConversationButtonProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The conversation pane's id, for `aria-controls`. */
  controls: string;
  ref?: Ref<HTMLButtonElement>;
  className?: string;
}

/** The chat bubble in the call's corner: opens and closes the conversation pane. */
export function ConversationButton({
  open,
  onOpenChange,
  controls,
  ref,
  className,
}: ConversationButtonProps) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={open ? 'Close conversation' : 'Open conversation'}
      aria-expanded={open}
      aria-controls={controls}
      title={open ? 'Close conversation' : 'Conversation'}
      onClick={() => onOpenChange(!open)}
      className={cn(
        'focus-visible:ring-ring/60 grid size-14 shrink-0 place-items-center rounded-full shadow-lg transition-colors outline-none focus-visible:ring-[3px]',
        open
          ? 'bg-primary text-primary-foreground hover:brightness-110'
          : 'text-foreground border border-white/10 bg-white/[0.08] backdrop-blur-md hover:bg-white/[0.14]',
        className
      )}
    >
      <MessageCircleIcon aria-hidden="true" className="size-6" />
    </button>
  );
}

interface ChatComposerProps {
  /** Focuses the input whenever this turns true (the pane opening). */
  focusWhen?: boolean;
  /** Called on Escape. */
  onEscape?: () => void;
  className?: string;
}

/**
 * The conversation's message box. Typing works during the greeting, but Send waits for it to
 * finish (the agent drops text sent earlier). The message shows up in the conversation once the
 * agent receives it.
 */
export function ChatComposer({ focusWhen, onEscape, className }: ChatComposerProps) {
  const { send } = useChat();
  const greetingDone = useGreetingDone();
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [sentTick, setSentTick] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (focusWhen) inputRef.current?.focus();
  }, [focusWhen]);

  useEffect(() => {
    if (!sentTick) return;
    const timer = setTimeout(() => setSentTick(false), 1400);
    return () => clearTimeout(timer);
  }, [sentTick]);

  const canSend = greetingDone && !sending && text.trim().length > 0;

  const submit = async () => {
    if (!canSend) return;
    const message = text.trim();
    setSending(true);
    try {
      await send(message);
      setText('');
      setSentTick(true);
    } catch (error) {
      console.error('Failed to send chat message:', error);
      toast.error('Message not sent', { description: 'Check your connection and try again.' });
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape' && onEscape) {
      // Keep the chat bubble's panel from also closing on this Escape.
      event.stopPropagation();
      onEscape();
    }
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
      className={cn(
        'flex h-12 items-center gap-2 rounded-full border border-white/12 bg-white/[0.06] pr-1.5 pl-4',
        'focus-within:border-primary/50',
        className
      )}
    >
      <label htmlFor="call-chat-input" className="sr-only">
        Message the agent
      </label>
      <input
        id="call-chat-input"
        ref={inputRef}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
        autoComplete="off"
        placeholder={greetingDone ? 'Type a message…' : 'Wait for the greeting to finish…'}
        className="placeholder:text-muted-foreground min-w-0 flex-1 bg-transparent text-[15px] outline-none"
      />
      <AnimatePresence>
        {sentTick && (
          <motion.span
            key="sent"
            role="status"
            initial={{ opacity: 0, x: 6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            className="text-primary flex shrink-0 items-center gap-1 text-xs font-medium"
          >
            <CheckIcon aria-hidden="true" className="size-3.5" />
            Sent
          </motion.span>
        )}
      </AnimatePresence>
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Send message"
        className="bg-primary text-primary-foreground focus-visible:ring-ring/60 grid size-9 shrink-0 place-items-center rounded-full transition-[opacity,filter] outline-none hover:brightness-110 focus-visible:ring-[3px] disabled:opacity-40"
      >
        <SendHorizontalIcon aria-hidden="true" className="size-4.5" />
      </button>
    </form>
  );
}
