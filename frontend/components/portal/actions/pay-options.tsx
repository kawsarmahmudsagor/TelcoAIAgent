'use client';

import { CreditCardIcon, WalletIcon } from 'lucide-react';
import { cn } from '@/lib/shadcn/utils';
import type { TxnChannel } from '@/lib/types/portal';

export interface PayOption {
  value: TxnChannel;
  label: string;
  /** A second muted line (e.g. the balance available). */
  hint?: string;
}

/** The wallets' brand colours as a small swatch; cards and the balance get an icon. */
function Mark({ value }: { value: TxnChannel }) {
  if (value === 'bkash' || value === 'nagad') {
    return (
      <span
        aria-hidden="true"
        className={cn('size-3 shrink-0 rounded-[4px]', value === 'bkash' ? 'bg-bkash' : 'bg-nagad')}
      />
    );
  }
  const Icon = value === 'card' ? CreditCardIcon : WalletIcon;
  return <Icon aria-hidden="true" className="text-muted-foreground size-3.5 shrink-0" />;
}

/** The reference's `.pay-option` tiles as a radio group (one per payment method). */
export function PayOptions({
  name,
  legend,
  options,
  value,
  onChange,
  className,
}: {
  name: string;
  legend: string;
  options: PayOption[];
  value: TxnChannel;
  onChange(value: TxnChannel): void;
  className?: string;
}) {
  return (
    <fieldset className={className}>
      <legend className="mb-[7px] block text-[11px] font-bold">{legend}</legend>
      <div
        className={cn(
          'grid gap-[9px]',
          options.length === 4 ? 'narrow:grid-cols-1 grid-cols-2' : 'grid-cols-3'
        )}
      >
        {options.map((option) => (
          <label
            key={option.value}
            className={cn(
              'rounded-button bg-surface border-line has-focus-visible:ring-ring/60 flex min-h-11 cursor-pointer items-center justify-center gap-2 border px-2 py-2.5 text-center text-[11px] font-bold has-focus-visible:ring-[3px]',
              option.hint && 'justify-start text-left',
              value === option.value && 'border-brand bg-tint-selected'
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            <Mark value={option.value} />
            <span className="min-w-0">
              {option.label}
              {option.hint && (
                <span className="text-muted-foreground block text-[10px] font-medium">
                  {option.hint}
                </span>
              )}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
