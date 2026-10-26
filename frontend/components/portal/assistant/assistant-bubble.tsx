'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Maximize2Icon, MinusIcon, XIcon } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { CHAT_PANEL_ID, useChatBubble } from '@/components/chat-bubble/chat-bubble-context';
import {
  AssistantChatHeader,
  AssistantConversation,
  BotAvatar,
} from '@/components/portal/assistant/assistant-chat';
import { useAssistant } from '@/components/portal/assistant/assistant-provider';
import { useOptionalPortalMe } from '@/components/portal/portal-me-context';
import { cn } from '@/lib/shadcn/utils';

const ASSISTANT_PATH = '/portal/assistant';
const INPUT_ID = 'assistant-bubble-input';

/**
 * The floating assistant on every portal page but the full assistant page: a launcher in the
 * bottom-right corner and the chat panel it opens (a full-screen sheet on phones). It never
 * connects on its own; the session starts when the customer types, picks a question or turns
 * the mic on. "Open full view" goes to /portal/assistant, which shows the same conversation;
 * a guest on the home page doesn't get it, since that page needs a login.
 */
export function AssistantBubble() {
  const pathname = usePathname();
  const { isOpen, open, close } = useChatBubble();
  const { isConnected, micEnabled } = useAssistant();
  const signedIn = useOptionalPortalMe() !== null;
  const reduceMotion = useReducedMotion();
  const hidden = pathname === ASSISTANT_PATH || pathname.startsWith(`${ASSISTANT_PATH}/`);

  // The full page takes over: the panel is closed when the customer comes back.
  useEffect(() => {
    if (hidden) close();
  }, [hidden, close]);

  useEffect(() => {
    if (isOpen && !hidden) document.getElementById(INPUT_ID)?.focus({ preventScroll: true });
  }, [isOpen, hidden]);

  if (hidden) return null;

  return (
    <>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="panel"
            id={CHAT_PANEL_ID}
            role="dialog"
            aria-label="Chat with Telco AI"
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
            style={{ transformOrigin: 'bottom right' }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') close();
            }}
            className={cn(
              'bg-surface border-line fixed z-50 flex flex-col overflow-hidden',
              'rounded-panel right-5 bottom-[92px] h-[min(620px,calc(100svh-120px))] w-[min(400px,calc(100vw-40px))] border shadow-[0_25px_70px_#0b102033]',
              'phone:inset-0 phone:h-auto phone:w-auto phone:rounded-none phone:border-0'
            )}
          >
            <AssistantChatHeader
              titleAs="h2"
              className="px-4 py-3.5"
              actions={
                <>
                  {signedIn && (
                    <Link
                      href={ASSISTANT_PATH}
                      aria-label="Open full view"
                      title="Open full view"
                      className="text-muted-foreground hover:bg-surface2 focus-visible:ring-ring/60 grid size-9 shrink-0 place-items-center rounded-[10px] outline-none focus-visible:ring-[3px] [&_svg]:size-4"
                    >
                      <Maximize2Icon aria-hidden="true" />
                    </Link>
                  )}
                  <button
                    type="button"
                    onClick={close}
                    aria-label={isConnected ? 'Minimise (the chat keeps going)' : 'Minimise'}
                    title="Minimise"
                    className="text-muted-foreground hover:bg-surface2 focus-visible:ring-ring/60 grid size-9 shrink-0 place-items-center rounded-[10px] outline-none focus-visible:ring-[3px] [&_svg]:size-4"
                  >
                    <MinusIcon aria-hidden="true" />
                  </button>
                </>
              }
            />
            <AssistantConversation compact inputId={INPUT_ID} />
          </motion.div>
        )}
      </AnimatePresence>

      <button
        type="button"
        onClick={isOpen ? close : open}
        aria-expanded={isOpen}
        aria-controls={CHAT_PANEL_ID}
        aria-label={
          isOpen ? 'Close chat' : isConnected ? 'Open chat (in progress)' : 'Chat with Telco AI'
        }
        className={cn(
          'focus-visible:ring-ring/60 fixed right-5 bottom-5 z-50 grid size-14 place-items-center rounded-full shadow-[0_12px_30px_#4f46e540] outline-none focus-visible:ring-[3px] motion-safe:transition-transform motion-safe:hover:-translate-y-0.5',
          isOpen && 'phone:hidden'
        )}
      >
        {isOpen ? (
          <span className="bg-brand grid size-14 place-items-center rounded-full text-white">
            <XIcon className="size-6" aria-hidden="true" />
          </span>
        ) : (
          <BotAvatar className="size-14 rounded-full [&_svg]:size-6" />
        )}
        {isConnected && !isOpen && (
          <span
            aria-hidden="true"
            className={cn(
              'ring-background absolute top-0.5 right-0.5 size-3.5 rounded-full ring-2',
              micEnabled ? 'bg-mint motion-safe:animate-pulse' : 'bg-mint'
            )}
          />
        )}
      </button>
    </>
  );
}
