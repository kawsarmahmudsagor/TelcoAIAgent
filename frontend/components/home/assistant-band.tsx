import {
  type LucideIcon,
  MessageSquareTextIcon,
  MicIcon,
  PackageIcon,
  SignalIcon,
  WalletIcon,
} from 'lucide-react';
import { LinkButton } from '@/components/portal/ui/link-button';

const CAN_DO: { icon: LucideIcon; text: string }[] = [
  { icon: WalletIcon, text: 'Tell you your balance, usage and when a pack runs out' },
  { icon: PackageIcon, text: 'Find a pack that fits and buy it once you confirm with a code' },
  { icon: MessageSquareTextIcon, text: 'Raise a complaint and tell you when it’s resolved' },
  { icon: SignalIcon, text: 'Check for network problems in your area' },
  { icon: MicIcon, text: 'Talk it through by voice, in Bangla or English' },
];

/** What Telco AI does, in plain words, and a way in. */
export function AssistantBand() {
  return (
    <section
      id="assistant"
      aria-labelledby="assistant-title"
      className="bg-surface border-line rounded-panel shadow-panel tablet:grid-cols-1 phone:p-6 grid scroll-mt-24 grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] gap-10 border p-10"
    >
      <div>
        <h2
          id="assistant-title"
          className="text-[26px] leading-tight font-extrabold tracking-[-0.03em]"
        >
          Telco AI, your assistant on call
        </h2>
        <p className="text-muted-foreground mt-3 max-w-[48ch] text-sm leading-relaxed">
          It knows your account, so you don’t repeat yourself. Anything that spends money waits for
          a code sent to your phone.
        </p>
        <LinkButton href="/portal/assistant" className="mt-6 min-h-11 px-5 text-sm">
          Ask Telco AI
        </LinkButton>
      </div>
      <ul className="flex flex-col gap-4 self-center">
        {CAN_DO.map(({ icon: Icon, text }) => (
          <li key={text} className="flex items-center gap-3.5 text-sm font-semibold">
            <span
              aria-hidden="true"
              className="bg-tint-green text-success grid size-9 shrink-0 place-items-center rounded-xl"
            >
              <Icon className="size-[18px]" />
            </span>
            {text}
          </li>
        ))}
      </ul>
    </section>
  );
}
