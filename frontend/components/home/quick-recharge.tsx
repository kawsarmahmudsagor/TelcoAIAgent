'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ArrowUpRightIcon,
  type LucideIcon,
  PackageIcon,
  ReceiptTextIcon,
  SparklesIcon,
} from 'lucide-react';
import { LinkButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';
import { formatTaka } from '@/lib/telco-format';

// The recharge form's chips (components/portal/recharge/recharge-form.tsx).
const AMOUNTS = [100, 200, 300, 500];

const SHORTCUTS: { href: string; label: string; note: string; icon: LucideIcon }[] = [
  {
    href: '/portal/packages',
    label: 'Buy a pack',
    note: 'Data, minutes and SMS',
    icon: PackageIcon,
  },
  {
    href: '/portal/recharge',
    label: 'Pay your bill',
    note: 'For postpaid numbers',
    icon: ReceiptTextIcon,
  },
  {
    href: '/portal/assistant',
    label: 'Ask Telco AI',
    note: 'Chat or talk, any time',
    icon: SparklesIcon,
  },
];

/**
 * "Recharge" with the portal's amount chips; the button opens the portal's recharge form with
 * that amount (logging in first when needed). Beside it, shortcuts into the portal.
 */
export function QuickRecharge() {
  const [amount, setAmount] = useState(200);

  return (
    <section
      id="recharge"
      aria-labelledby="recharge-title"
      className="tablet:grid-cols-1 grid scroll-mt-24 grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-4"
    >
      <div className="bg-surface border-line rounded-panel shadow-panel flex flex-col gap-4 border p-6">
        <div>
          <h2 id="recharge-title" className="text-lg font-bold tracking-[-0.02em]">
            Recharge
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Pay with bKash, Nagad or card. You confirm with a code sent to your phone.
          </p>
        </div>
        <fieldset>
          <legend className="sr-only">Amount</legend>
          <div className="flex flex-wrap gap-2">
            {AMOUNTS.map((value) => (
              <label key={value} className="cursor-pointer">
                <input
                  type="radio"
                  name="home-recharge-amount"
                  value={value}
                  checked={amount === value}
                  onChange={() => setAmount(value)}
                  className="peer sr-only"
                />
                <span
                  className={cn(
                    'rounded-button border-line text-foreground inline-flex min-h-11 items-center border px-4 text-sm font-bold tabular-nums',
                    'peer-checked:border-brand peer-checked:bg-tint-selected peer-checked:text-brand-text',
                    'peer-focus-visible:ring-ring/60 peer-focus-visible:ring-[3px]'
                  )}
                >
                  {formatTaka(value)}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <LinkButton
          href={`/portal/recharge?amount=${amount}`}
          className="min-h-11 self-start px-5 text-sm"
        >
          Recharge {formatTaka(amount)}
        </LinkButton>
      </div>

      <ul className="grid gap-3">
        {SHORTCUTS.map(({ href, label, note, icon: Icon }) => (
          <li key={href + label}>
            <Link
              href={href}
              className="group bg-surface border-line rounded-panel hover:border-chip-border focus-visible:ring-ring/60 flex min-h-[72px] items-center gap-4 border px-5 py-3 outline-none focus-visible:ring-[3px]"
            >
              <span
                aria-hidden="true"
                className="bg-tint-purple text-brand-text grid size-10 shrink-0 place-items-center rounded-xl"
              >
                <Icon className="size-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-bold">{label}</span>
                <span className="text-muted-foreground block text-xs">{note}</span>
              </span>
              <ArrowUpRightIcon
                aria-hidden="true"
                className="text-muted-foreground group-hover:text-brand-text size-4"
              />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
