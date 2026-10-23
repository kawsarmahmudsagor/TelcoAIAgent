import Link from 'next/link';
import { GaugeIcon, GiftIcon, LifeBuoyIcon, type LucideIcon, SignalIcon } from 'lucide-react';

const NETWORK_PROMPT = 'Is there a network problem in my area?';

const TILES: { href: string; title: string; text: string; icon: LucideIcon }[] = [
  {
    href: '/portal/support',
    title: 'Support cases',
    text: 'Raise a complaint and follow it until it’s resolved.',
    icon: LifeBuoyIcon,
  },
  {
    href: `/portal/assistant?q=${encodeURIComponent(NETWORK_PROMPT)}`,
    title: 'Network status',
    text: 'Ask Telco AI about outages and slow speeds near you.',
    icon: SignalIcon,
  },
  {
    href: '/portal/offers',
    title: 'Offers & rewards',
    text: 'Spend reward points and see offers made for you.',
    icon: GiftIcon,
  },
  {
    href: '/portal/balance',
    title: 'Balance & usage',
    text: 'See what you have left and where it went.',
    icon: GaugeIcon,
  },
];

/** "How can we help?": four ways into the portal (each logs in first when needed). */
export function HelpTiles() {
  return (
    <section id="help" aria-labelledby="help-title" className="scroll-mt-24">
      <h2 id="help-title" className="mb-5 text-[26px] font-extrabold tracking-[-0.03em]">
        How can we help?
      </h2>
      <ul className="tablet:grid-cols-2 narrow:grid-cols-1 grid grid-cols-4 gap-4">
        {TILES.map(({ href, title, text, icon: Icon }) => (
          <li key={title}>
            <Link
              href={href}
              className="bg-surface border-line rounded-panel hover:border-chip-border focus-visible:ring-ring/60 flex h-full flex-col gap-3 border p-5 outline-none focus-visible:ring-[3px]"
            >
              <Icon aria-hidden="true" className="text-brand-text size-6" />
              <span className="text-[15px] font-bold">{title}</span>
              <span className="text-muted-foreground text-sm leading-snug">{text}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
