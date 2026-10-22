import Link from 'next/link';
import { ArrowUpRightIcon, GiftIcon, PackageIcon, SparklesIcon } from 'lucide-react';
import { SectionHead } from '@/components/portal/ui/section-head';

const ACTIONS = [
  { href: '/portal/recharge', icon: ArrowUpRightIcon, title: 'Recharge', line: 'Top up balance' },
  {
    href: '/portal/packages',
    icon: PackageIcon,
    title: 'Buy a pack',
    line: 'Data, minutes & more',
  },
  { href: '/portal/offers', icon: GiftIcon, title: 'My offers', line: 'Deals picked for you' },
  {
    href: '/portal/assistant',
    icon: SparklesIcon,
    title: 'Ask Telco AI',
    line: 'Instant help, 24/7',
  },
];

/** The four shortcuts under "Quick actions". */
export function QuickActions() {
  return (
    <section aria-labelledby="quick-actions">
      <SectionHead
        title={<span id="quick-actions">Quick actions</span>}
        description="Your most-used services, one tap away."
      />
      <ul className="tablet:grid-cols-2 phone:gap-[9px] mb-5 grid grid-cols-4 gap-[18px]">
        {ACTIONS.map(({ href, icon: Icon, title, line }) => (
          <li key={href} className="min-w-0">
            <Link
              href={href}
              className="bg-surface border-line text-foreground focus-visible:ring-ring/60 phone:gap-[9px] phone:p-3 flex h-full items-center gap-3 rounded-[15px] border p-4 outline-none hover:border-[#b7b2ff] focus-visible:ring-[3px] motion-safe:transition-[border-color,transform] motion-safe:duration-150 motion-safe:hover:-translate-y-0.5"
            >
              <span
                aria-hidden="true"
                className="bg-tint-purple text-brand phone:size-[34px] grid size-10 shrink-0 place-items-center rounded-xl dark:text-[#a9a3ff] [&_svg]:size-[19px]"
              >
                <Icon />
              </span>
              <span className="min-w-0">
                <strong className="phone:text-[10px] block text-[11px]">{title}</strong>
                <span className="text-muted-foreground phone:text-[9px] mt-[3px] block text-[10px]">
                  {line}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
