'use client';

import { useSearchParams } from 'next/navigation';
import { LifeBuoyIcon, PackageIcon, WalletIcon } from 'lucide-react';
import {
  AssistantChatHeader,
  AssistantConversation,
} from '@/components/portal/assistant/assistant-chat';
import { useAssistant } from '@/components/portal/assistant/assistant-provider';
import { PopularQuestionList } from '@/components/portal/assistant/suggested-questions';
import { IconTile, type IconTileTone } from '@/components/portal/ui/icon-tile';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';

const HELP_TOPICS: { icon: typeof WalletIcon; tone: IconTileTone; title: string; line: string }[] =
  [
    { icon: WalletIcon, tone: 'purple', title: 'Balance & usage', line: 'Personal account info' },
    { icon: PackageIcon, tone: 'green', title: 'Packages & offers', line: 'Find your best fit' },
    {
      icon: LifeBuoyIcon,
      tone: 'orange',
      title: 'Support & issues',
      line: 'Track or raise a case',
    },
  ];

/**
 * The full AI assistant: the reference's chat panel beside a 280px aside (popular questions,
 * what it can help with). The chat is the portal's one session, so a conversation started in
 * the bubble carries on here. `?q=` prefills the message box.
 */
export function AssistantPage() {
  const { sendText } = useAssistant();
  const q = useSearchParams().get('q') ?? undefined;

  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] mb-[5px] text-[25px] font-bold tracking-[-0.8px]">
          Meet Telco AI
        </h1>
        <p className="text-muted-foreground text-xs">
          Your personal telco assistant — balance, packages, recharge questions and support, in
          English or Bangla. Type, or turn on the mic and talk.
        </p>
      </div>

      <div className="tablet:grid-cols-[minmax(0,1fr)_240px] phone:grid-cols-1 grid grid-cols-[minmax(0,1fr)_280px] items-start gap-[18px]">
        <section
          aria-label="Chat with Telco AI"
          className="bg-surface border-line rounded-panel shadow-panel phone:h-[min(640px,calc(100svh-150px))] flex h-[clamp(480px,calc(100svh-210px),700px)] min-w-0 flex-col overflow-hidden border"
        >
          <AssistantChatHeader />
          {/* A new ?q= gives a fresh message box with that text. */}
          <AssistantConversation key={q ?? ''} initialText={q} inputId="assistant-page-input" />
        </section>

        <aside className="phone:grid-cols-2 narrow:grid-cols-1 phone:grid phone:items-start flex min-w-0 flex-col gap-3.5">
          <Panel>
            <PanelHeader title="Popular questions" className="mb-1" />
            <PopularQuestionList onAsk={sendText} />
          </Panel>
          <Panel>
            <PanelHeader title="I can help you with" className="mb-[13px]" />
            <ul className="flex flex-col gap-3">
              {HELP_TOPICS.map(({ icon, tone, title, line }) => (
                <li key={title} className="flex items-center gap-2.5">
                  <IconTile icon={icon} tone={tone} className="size-8" />
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold">{title}</p>
                    <p className="text-muted-foreground text-[10px]">{line}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        </aside>
      </div>
    </>
  );
}
