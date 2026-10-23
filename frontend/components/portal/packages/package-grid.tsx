'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Loader2Icon, PackageIcon } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';
import { type PayOption, PayOptions } from '@/components/portal/actions/pay-options';
import { usePortalAction } from '@/components/portal/actions/use-portal-action';
import { PackageCard, packageContents, validity } from '@/components/portal/packages/package-card';
import { usePortalMe } from '@/components/portal/portal-me-context';
import { PortalButton } from '@/components/portal/ui/link-button';
import { Panel } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { formatTaka } from '@/lib/telco-format';
import type { PackageKind, PackageView, TxnChannel } from '@/lib/types/portal';

type Filter = 'all' | PackageKind;

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All packs' },
  { value: 'data', label: 'Internet' },
  { value: 'voice', label: 'Minutes' },
  { value: 'bundle', label: 'Bundles' },
  { value: 'sms', label: 'SMS' },
];

const GRID = 'tablet:grid-cols-2 phone:grid-cols-1 grid grid-cols-3 gap-[18px]';

/** Filters, the pack grid and the pay-from chooser that starts the OTP flow. */
export function PackageGrid() {
  const packages = usePortalQuery('packages', () => portalApi.packages());
  const highlight = useSearchParams().get('highlight');
  const [filter, setFilter] = useState<Filter>('all');
  const [buying, setBuying] = useState<PackageView | null>(null);
  const { start, dialog } = usePortalAction();
  const highlightRef = useRef<HTMLLIElement>(null);
  const scrolledFor = useRef<string | null>(null);

  // Once the packs load, bring the linked pack into view (once per highlight).
  const found = Boolean(highlight && packages.data?.some((p) => p.code === highlight));
  useEffect(() => {
    if (!found || scrolledFor.current === highlight) return;
    scrolledFor.current = highlight;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    highlightRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
  }, [found, highlight]);

  const shown = (packages.data ?? []).filter(
    (p) => filter === 'all' || p.kind === filter || p.code === highlight
  );

  return (
    <>
      <div role="group" aria-label="Filter packs" className="mb-[18px] flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <PortalButton
            key={f.value}
            variant={filter === f.value ? 'primary' : 'outline'}
            aria-pressed={filter === f.value}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </PortalButton>
        ))}
      </div>

      {packages.data ? (
        shown.length === 0 ? (
          <Panel className="flex items-center gap-3">
            <PackageIcon className="text-muted-foreground size-5 shrink-0" aria-hidden="true" />
            <p className="text-muted-foreground text-sm">
              No packs of this kind right now. Try another filter.
            </p>
          </Panel>
        ) : (
          <ul className={GRID}>
            {shown.map((pkg) => (
              <PackageCard
                key={pkg.code}
                ref={pkg.code === highlight ? highlightRef : undefined}
                pkg={pkg}
                highlighted={pkg.code === highlight}
                onBuy={() => setBuying(pkg)}
              />
            ))}
          </ul>
        )
      ) : packages.error && !packages.loading ? (
        <Panel>
          <LoadError what="The packs" error={packages.error} onRetry={packages.reload} />
        </Panel>
      ) : (
        <ul className={GRID} aria-hidden="true">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <li
              key={i}
              className="bg-surface border-line rounded-metric flex flex-col gap-3 border p-[18px]"
            >
              <Bone className="h-4 w-16" />
              <Bone className="h-6 w-32" />
              <Bone className="h-3 w-40" />
              <Bone className="mt-3 h-9 w-full" />
            </li>
          ))}
        </ul>
      )}

      <PayFromChooser
        pkg={buying}
        onClose={() => setBuying(null)}
        onPay={async (pkg, payFrom) => {
          await start({ kind: 'purchase', package_code: pkg.code, pay_from: payFrom });
          setBuying(null);
        }}
      />
      {dialog}
    </>
  );
}

/** The small "how do you want to pay?" step before the code is sent. */
function PayFromChooser({
  pkg,
  onClose,
  onPay,
}: {
  pkg: PackageView | null;
  onClose(): void;
  onPay(pkg: PackageView, payFrom: TxnChannel): Promise<void>;
}) {
  const me = usePortalMe();
  const postpaid = me.plan_type === 'postpaid';
  const summary = usePortalQuery('summary', portalApi.summary);
  const [payFrom, setPayFrom] = useState<TxnChannel>('balance');
  const [sending, setSending] = useState(false);
  const name = useId();

  const balance = summary.data?.main_balance;
  const options: PayOption[] = [
    {
      value: 'balance',
      label: postpaid ? 'Add to bill' : 'Main balance',
      hint: postpaid
        ? 'Paid with your next bill'
        : balance !== undefined
          ? `${formatTaka(balance)} available`
          : undefined,
    },
    { value: 'bkash', label: 'bKash', hint: 'Pay now' },
    { value: 'nagad', label: 'Nagad', hint: 'Pay now' },
    { value: 'card', label: 'Card', hint: 'Pay now' },
  ];

  return (
    <DialogPrimitive.Root
      open={pkg !== null}
      onOpenChange={(open) => {
        if (!open && !sending) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="data-[state=open]:animate-in data-[state=open]:fade-in-0 bg-scrim fixed inset-0 z-50" />
        {pkg && (
          <DialogPrimitive.Content className="bg-surface border-line data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 phone:p-5 fixed top-1/2 left-1/2 z-[51] w-[min(420px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-[18px] border p-6 shadow-[0_25px_70px_#0003] outline-none">
            <DialogPrimitive.Title className="mb-[7px] text-lg font-bold tracking-[-0.3px]">
              Buy {pkg.name}
            </DialogPrimitive.Title>
            <DialogPrimitive.Description className="text-muted-foreground mb-4 text-xs">
              {formatTaka(pkg.price)} · {packageContents(pkg)} · {validity(pkg.validity_days)}
            </DialogPrimitive.Description>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                if (sending) return;
                setSending(true);
                await onPay(pkg, payFrom);
                setSending(false);
              }}
            >
              <PayOptions
                name={name}
                legend="Pay from"
                options={options}
                value={payFrom}
                onChange={setPayFrom}
              />
              <p className="text-muted-foreground mt-3 text-[10px]">
                We’ll text you a code to confirm. Demo only — no real payment.
              </p>
              <div className="mt-[18px] flex justify-end gap-2">
                <PortalButton variant="outline" onClick={onClose} disabled={sending}>
                  Cancel
                </PortalButton>
                <PortalButton type="submit" disabled={sending}>
                  {sending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                  {sending ? 'Sending your code…' : 'Continue'}
                </PortalButton>
              </div>
            </form>
          </DialogPrimitive.Content>
        )}
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
