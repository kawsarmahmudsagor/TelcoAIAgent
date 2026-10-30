'use client';

import { type ReactNode, useMemo, useState } from 'react';
import {
  ArrowUpIcon,
  AsteriskIcon,
  DownloadIcon,
  HistoryIcon,
  Loader2Icon,
  MicIcon,
  MicOffIcon,
  PhoneIcon,
  PhoneOffIcon,
  Volume2Icon,
  VolumeXIcon,
} from 'lucide-react';
import { Streamdown } from 'streamdown';
import type { ReceivedMessage } from '@livekit/components-react';
import { AgentChatTranscript } from '@/components/agents-ui/agent-chat-transcript';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { useCallAudio } from '@/components/app/call/call-audio-provider';
import { statusLabel } from '@/components/app/call/status';
import { useChatBubble } from '@/components/chat-bubble/chat-bubble-context';
import { ExportConversationDialog } from '@/components/customer/export-conversation-dialog';
import { useAssistant } from '@/components/portal/assistant/assistant-provider';
import { CaseCard } from '@/components/portal/assistant/cards/case-card';
import { ConfirmCard } from '@/components/portal/assistant/cards/confirm-card';
import { PackageCards, buyMessage } from '@/components/portal/assistant/cards/package-cards';
import { ConversationHistory } from '@/components/portal/assistant/conversation-history';
import {
  GUEST_QUESTIONS,
  GUEST_QUESTIONS_EN,
  POPULAR_QUESTIONS,
  POPULAR_QUESTIONS_EN,
  QuestionChips,
} from '@/components/portal/assistant/suggested-questions';
import { useOptionalPortalMe } from '@/components/portal/portal-me-context';
import { exportVisitorConversation } from '@/lib/public-conversations';
import { cn } from '@/lib/shadcn/utils';
import { placeAfterTurn } from '@/lib/telco-topics';

const timeFormat = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' });

/** The reference's gradient bot mark. */
export function BotAvatar({ size = 'md', className }: { size?: 'sm' | 'md'; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'from-brand to-mint grid shrink-0 place-items-center bg-linear-135 text-white',
        size === 'md'
          ? 'size-[39px] rounded-[13px] [&_svg]:size-5'
          : 'size-[29px] rounded-[9px] [&_svg]:size-4',
        className
      )}
    >
      <AsteriskIcon strokeWidth={2.6} />
    </span>
  );
}

/**
 * The chat panel's header: the assistant's name, its live status, the chat history toggle, and
 * the speaker toggle while connected, a call button that starts a voice conversation (as
 * "Talk instead of typing" does) while the mic is off, and an export button for the ended chat
 * on screen (disabled while one is live). `actions` go on the right (e.g. the
 * bubble's buttons).
 */
export function AssistantChatHeader({
  titleAs: Title = 'h2',
  actions,
  className,
}: {
  titleAs?: 'h2' | 'h3';
  actions?: ReactNode;
  className?: string;
}) {
  const {
    isConnected,
    connecting,
    micEnabled,
    agentState,
    historyOpen,
    setHistoryOpen,
    toggleMic,
    voiceMode,
    replyLanguage,
    exportableId,
  } = useAssistant();
  const { muted, toggleMuted } = useCallAudio();
  const { visitorId } = useChatBubble();
  const [exportOpen, setExportOpen] = useState(false);
  const canExport = Boolean(exportableId && visitorId);

  let status = 'Usually replies instantly';
  if (connecting) status = 'Connecting…';
  else if (isConnected && micEnabled) status = statusLabel(agentState);
  else if (isConnected) status = agentState === 'thinking' ? 'Typing…' : 'Connected';

  return (
    <div
      className={cn(
        'border-line phone:px-4 phone:py-3.5 flex items-center gap-[11px] border-b px-[21px] py-[18px]',
        className
      )}
    >
      <BotAvatar />
      <div className="min-w-0 flex-1">
        <Title className="truncate text-[13px] font-bold">Telco AI Assistant</Title>
        <p className="text-muted-foreground truncate text-[11px]" aria-live="polite">
          <span className="text-success font-semibold">● Online</span> · {status}
          {replyLanguage && (
            <>
              {' · '}
              <span lang={replyLanguage}>{replyLanguage === 'en' ? 'English' : 'বাংলা'}</span>
            </>
          )}
        </p>
      </div>
      <StartAudioButton label="Allow audio" size="sm" />
      {voiceMode !== 'off' && !micEnabled && !connecting && (
        <HeaderButton label="Talk to the assistant" onClick={toggleMic}>
          <PhoneIcon aria-hidden="true" />
        </HeaderButton>
      )}
      <HeaderButton
        label={canExport ? 'Export chat' : 'Export chat (once the chat has ended)'}
        onClick={() => setExportOpen(true)}
        disabled={!canExport}
      >
        <DownloadIcon aria-hidden="true" />
      </HeaderButton>
      <HeaderButton
        label={historyOpen ? 'Back to the chat' : 'Chat history'}
        onClick={() => setHistoryOpen(!historyOpen)}
        pressed={historyOpen}
      >
        <HistoryIcon aria-hidden="true" />
      </HeaderButton>
      {isConnected && (
        <HeaderButton
          label={muted ? 'Turn the assistant’s voice on' : 'Mute the assistant’s voice'}
          onClick={toggleMuted}
          pressed={muted}
        >
          {muted ? <VolumeXIcon aria-hidden="true" /> : <Volume2Icon aria-hidden="true" />}
        </HeaderButton>
      )}
      {actions}
      {exportableId && visitorId && (
        <ExportConversationDialog
          open={exportOpen}
          onOpenChange={setExportOpen}
          defaultLanguage={replyLanguage}
          fetchExport={(lang) => exportVisitorConversation(visitorId, exportableId, lang)}
        />
      )}
    </div>
  );
}

/** A 36px icon button for the chat header. */
export function HeaderButton({
  label,
  onClick,
  pressed,
  disabled,
  children,
}: {
  label: string;
  onClick(): void;
  pressed?: boolean;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      className="text-muted-foreground hover:bg-surface2 focus-visible:ring-ring/60 grid size-9 shrink-0 place-items-center rounded-[10px] outline-none focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-40 motion-safe:transition-colors [&_svg]:size-4"
    >
      {children}
    </button>
  );
}

function MessageRow({ message }: { message: ReceivedMessage }) {
  const isUser = Boolean(message.from?.isLocal);
  return (
    <div
      className={cn(
        'flex max-w-[82%] items-end gap-2',
        isUser ? 'ml-auto flex-row-reverse' : 'mr-auto'
      )}
    >
      {!isUser && <BotAvatar size="sm" />}
      <div
        className={cn(
          'min-w-0 border px-3.5 py-3 text-[13px] leading-[1.6] wrap-break-word',
          isUser
            ? 'bg-brand border-brand rounded-[14px_14px_4px_14px] text-white'
            : 'bg-surface border-line rounded-[14px_14px_14px_4px]'
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.message}</p>
        ) : (
          <Streamdown className="[&_ol]:my-1 [&_p]:my-0 [&_p+p]:mt-2 [&_ul]:my-1">
            {message.message}
          </Streamdown>
        )}
        <small
          className={cn(
            'mt-[5px] block text-[10px]',
            isUser ? 'text-white/75' : 'text-muted-foreground'
          )}
        >
          {timeFormat.format(new Date(message.timestamp))}
        </small>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div
      className="mr-auto flex items-end gap-2"
      role="status"
      aria-label="The assistant is typing"
    >
      <BotAvatar size="sm" />
      <div className="bg-surface border-line flex h-[42px] items-center gap-1 rounded-[14px_14px_14px_4px] border px-4">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            aria-hidden="true"
            className="bg-muted-foreground/60 size-1.5 rounded-full motion-safe:animate-bounce"
            style={{ animationDelay: `${i * 140}ms`, animationDuration: '1s' }}
          />
        ))}
      </div>
    </div>
  );
}

function QueuedRow({ text }: { text: string }) {
  return (
    <div className="ml-auto flex max-w-[82%] flex-col items-end gap-1">
      <div className="bg-brand/60 rounded-[14px_14px_4px_14px] px-3.5 py-3 text-[13px] leading-[1.6] whitespace-pre-wrap text-white">
        {text}
      </div>
      <small className="text-muted-foreground inline-flex items-center gap-1 text-[10px]">
        <Loader2Icon className="size-3 animate-spin" aria-hidden="true" />
        Sends when the assistant is ready
      </small>
    </div>
  );
}

/**
 * Opens each new chat: the customer picks the language every reply will be in (a start made
 * before the pick waits for it).
 */
function LanguagePicker({ compact }: { compact: boolean }) {
  const { chooseReplyLanguage } = useAssistant();
  return (
    <div className="h-full overflow-y-auto">
      <div
        className={cn(
          'flex min-h-full flex-col items-center justify-center gap-4 text-center',
          compact ? 'p-4' : 'p-5'
        )}
      >
        <BotAvatar />
        <h3 className="text-[13px] font-bold">
          Choose a language / <span lang="bn">ভাষা বেছে নিন</span>
        </h3>
        <div className="flex w-full max-w-[280px] flex-col gap-2.5">
          {(
            [
              ['en', 'English'],
              ['bn', 'বাংলা'],
            ] as const
          ).map(([language, label]) => (
            <button
              key={language}
              type="button"
              lang={language}
              onClick={() => chooseReplyLanguage(language)}
              className="border-line bg-surface text-foreground hover:border-brand focus-visible:ring-ring/60 min-h-11 rounded-[10px] border px-4 text-[13px] font-bold outline-none focus-visible:ring-[3px] motion-safe:transition-colors"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ compact }: { compact: boolean }) {
  // Null for a guest on the home page.
  const me = useOptionalPortalMe();
  const { connecting, isConnected, sendText, toggleMic, voiceMode, replyLanguage } = useAssistant();
  const english = replyLanguage === 'en';

  if (connecting || isConnected) {
    return (
      <div className="grid h-full place-content-center gap-3 p-6 text-center" role="status">
        <Loader2Icon className="text-brand mx-auto size-5 animate-spin" aria-hidden="true" />
        <p className="text-muted-foreground text-xs">
          {isConnected ? 'The assistant is joining…' : 'Connecting to the assistant…'}
        </p>
      </div>
    );
  }

  // Scrolls when the greeting outgrows a short widget; justify-end on a fixed
  // height would push the overflow up over the header.
  return (
    <div className="h-full overflow-y-auto">
      <div className={cn('flex min-h-full flex-col justify-end gap-4', compact ? 'p-4' : 'p-5')}>
        <div className="flex max-w-[86%] items-end gap-2">
          <BotAvatar size="sm" />
          <div className="bg-surface border-line rounded-[14px_14px_14px_4px] border px-3.5 py-3 text-[13px] leading-[1.6]">
            {english ? (
              <p lang="en">
                {me
                  ? `Assalamu alaikum, ${me.first_name}! I’m telco’s assistant. I can help you check your balance and usage, find a package or recharge.`
                  : 'Assalamu alaikum! I’m telco’s assistant. I can help you find a package, check the network in your area, or answer questions about SIMs, stores and our policies. Log in to see your balance or buy a package.'}
              </p>
            ) : me ? (
              <p lang="bn">
                আসসালামু আলাইকুম, {me.first_name}! আমি telco-এর অ্যাসিস্ট্যান্ট। ব্যালেন্স চেক,
                ইউসেজের হিসাব, প্যাকেজ খোঁজা বা রিচার্জ, সবকিছুতেই হেল্প করতে পারি।
              </p>
            ) : (
              <p lang="bn">
                আসসালামু আলাইকুম! আমি telco-এর অ্যাসিস্ট্যান্ট। প্যাকেজ খোঁজা, আপনার এলাকার
                নেটওয়ার্ক চেক, বা সিম, স্টোর আর আমাদের পলিসি নিয়ে যেকোনো প্রশ্নে হেল্প করতে পারি।
                নিজের ব্যালেন্স দেখতে বা প্যাকেজ কিনতে লগইন করুন।
              </p>
            )}
            <p lang={english ? 'en' : 'bn'} className="mt-2">
              {english ? 'How can I help?' : 'কীভাবে হেল্প করতে পারি?'}
            </p>
            <QuestionChips
              onAsk={sendText}
              questions={
                english
                  ? me
                    ? POPULAR_QUESTIONS_EN
                    : GUEST_QUESTIONS_EN
                  : me
                    ? POPULAR_QUESTIONS
                    : GUEST_QUESTIONS
              }
              className="mt-2.5"
            />
          </div>
        </div>
        {voiceMode !== 'off' && (
          <button
            type="button"
            onClick={toggleMic}
            className="border-line bg-surface text-foreground hover:border-mint focus-visible:ring-ring/60 mx-auto inline-flex min-h-10 items-center gap-2 rounded-full border px-4 text-xs font-bold outline-none focus-visible:ring-[3px] motion-safe:transition-colors"
          >
            <span className="bg-tint-green text-mint grid size-6 place-items-center rounded-full">
              <MicIcon className="size-3.5" aria-hidden="true" />
            </span>
            Talk instead of typing
          </button>
        )}
      </div>
    </div>
  );
}

function Composer({
  initialText,
  inputId,
  locked = false,
}: {
  initialText?: string;
  inputId: string;
  /** The language picker is showing: nothing can be sent until the pick. */
  locked?: boolean;
}) {
  const { sendText, toggleMic, micEnabled, isConnected, connecting, voiceMode, end } =
    useAssistant();
  const [text, setText] = useState(initialText ?? '');

  const micLabel = !isConnected
    ? 'Start a voice chat'
    : micEnabled
      ? 'Turn the microphone off'
      : 'Turn the microphone on';

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (locked || !text.trim()) return;
        sendText(text);
        setText('');
      }}
      className="bg-surface phone:p-3 flex gap-2 p-3.5"
    >
      {voiceMode !== 'off' && (
        <button
          type="button"
          onClick={toggleMic}
          disabled={connecting || locked}
          aria-label={micLabel}
          title={micLabel}
          aria-pressed={isConnected ? micEnabled : undefined}
          className={cn(
            'focus-visible:ring-ring/60 relative grid w-[43px] shrink-0 place-items-center rounded-[10px] border outline-none focus-visible:ring-[3px] disabled:opacity-55 motion-safe:transition-colors [&_svg]:size-[18px]',
            micEnabled
              ? 'bg-mint border-mint text-white'
              : 'border-line bg-surface2 text-muted-foreground hover:text-foreground'
          )}
        >
          {micEnabled && (
            <span
              aria-hidden="true"
              className="border-mint absolute inset-0 rounded-[10px] border-2 motion-safe:animate-ping motion-reduce:hidden"
              style={{ animationDuration: '1.8s' }}
            />
          )}
          {micEnabled || !isConnected ? (
            <MicIcon aria-hidden="true" />
          ) : (
            <MicOffIcon aria-hidden="true" />
          )}
        </button>
      )}
      {isConnected && (
        <button
          type="button"
          onClick={end}
          aria-label="End the chat"
          title="End the chat"
          className="bg-red border-red focus-visible:ring-ring/60 grid w-[43px] shrink-0 place-items-center rounded-[10px] border text-white outline-none hover:opacity-90 focus-visible:ring-[3px] motion-safe:transition-opacity [&_svg]:size-[18px]"
        >
          <PhoneOffIcon aria-hidden="true" />
        </button>
      )}
      <label htmlFor={inputId} className="sr-only">
        Message the assistant
      </label>
      <input
        id={inputId}
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoComplete="off"
        disabled={locked}
        placeholder={
          locked ? 'Choose a language first / আগে ভাষা বেছে নিন' : 'Ask anything… / বাংলায় লিখুন'
        }
        className="border-line bg-surface2 text-foreground placeholder:text-muted-foreground focus-visible:border-brand focus-visible:ring-ring/30 min-w-0 flex-1 rounded-[10px] border px-3 py-3 text-[13px] outline-none focus-visible:ring-[3px] disabled:opacity-55"
      />
      <button
        type="submit"
        disabled={locked || !text.trim()}
        aria-label="Send message"
        className="bg-brand focus-visible:ring-ring/60 grid w-[43px] shrink-0 place-items-center rounded-[10px] text-white outline-none focus-visible:ring-[3px] disabled:opacity-55 [&_svg]:size-[18px]"
      >
        <ArrowUpIcon aria-hidden="true" />
      </button>
    </form>
  );
}

type Placed = { key: string; revealedAt: number; node: ReactNode };

/**
 * The conversation and its message box: transcript (with the agent's cards pinned to their
 * turns), typing indicator, queued text, mic toggle and input. Shared by the assistant page and
 * the bubble's panel; both read the one session from AssistantProvider.
 */
export function AssistantConversation({
  initialText,
  compact = false,
  inputId,
}: {
  /** Prefills the message box (e.g. `?q=`). */
  initialText?: string;
  /** The bubble's narrower panel. */
  compact?: boolean;
  inputId: string;
}) {
  const {
    messages,
    cards,
    confirm,
    agentState,
    queued,
    sendText,
    historyOpen,
    replyLanguage,
    languagePending,
  } = useAssistant();

  const placed = useMemo<Placed[]>(() => {
    const items: Placed[] = cards.map((card) => ({
      key: `card-${card.id}`,
      revealedAt: card.revealedAt,
      node:
        card.kind === 'packages' ? (
          <PackageCards data={card.data} onBuy={(pkg) => sendText(buyMessage(pkg))} />
        ) : (
          <CaseCard data={card.data} />
        ),
    }));
    if (confirm) {
      items.push({
        key: `confirm-${confirm.action_id}`,
        revealedAt: confirm.revealedAt,
        node: <ConfirmCard key={confirm.action_id} confirm={confirm} />,
      });
    }
    return items;
  }, [cards, confirm, sendText]);

  const placement = useMemo(() => placeAfterTurn(messages, placed), [messages, placed]);
  const renderPlaced = (items: Placed[] | undefined) =>
    items?.length ? (
      <div className="phone:pl-0 flex flex-col gap-3 pl-[37px]">
        {items.map((item) => (
          <div key={item.key}>{item.node}</div>
        ))}
      </div>
    ) : undefined;

  const empty = messages.length === 0 && placed.length === 0 && queued.length === 0;
  // A new chat opens on the picker; so does a start made before the pick (a chip from the
  // page's list, a notification, the call button) or in a chat from before the pick.
  const picking = replyLanguage === null && (empty || languagePending);
  const trailing =
    placement.unplaced.length > 0 || queued.length > 0 ? (
      <div className="flex flex-col gap-3.5">
        {renderPlaced(placement.unplaced)}
        {queued.map((text, i) => (
          <QueuedRow key={`${i}-${text}`} text={text} />
        ))}
      </div>
    ) : undefined;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="bg-chat-canvas min-h-0 flex-1">
        {historyOpen ? (
          <ConversationHistory compact={compact} />
        ) : picking ? (
          <LanguagePicker compact={compact} />
        ) : empty ? (
          <EmptyState compact={compact} />
        ) : (
          <AgentChatTranscript
            agentState={agentState}
            messages={messages}
            renderMessage={(message) => <MessageRow message={message} />}
            renderAfterMessage={(message) => renderPlaced(placement.byMessageId.get(message.id))}
            trailingContent={trailing}
            thinkingContent={<TypingIndicator />}
            className={cn(
              'h-full **:data-[slot=message-scroller-content]:gap-3.5',
              compact
                ? '**:data-[slot=message-scroller-content]:p-4'
                : '**:data-[slot=message-scroller-content]:p-5'
            )}
          />
        )}
      </div>
      <div className="border-line border-t">
        <Composer initialText={initialText} inputId={inputId} locked={picking && !historyOpen} />
        <p className="text-muted-foreground bg-surface phone:px-3 px-3.5 pb-3 text-[10px]">
          Never share your OTP or payment PIN in chat.
        </p>
      </div>
    </div>
  );
}
