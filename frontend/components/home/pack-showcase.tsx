'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { PackageIcon } from 'lucide-react';
import { PackageCard } from '@/components/portal/packages/package-card';
import { PortalButton, SmallLink } from '@/components/portal/ui/link-button';
import { Panel } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { ApiError } from '@/lib/api-client';
import { portalApi } from '@/lib/portal-api';
import type { PackageKind, PackageView } from '@/lib/types/portal';

type Filter = 'all' | PackageKind;

// Same filters and names as the portal's packs page.
const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All packs' },
  { value: 'data', label: 'Internet' },
  { value: 'voice', label: 'Minutes' },
  { value: 'bundle', label: 'Bundles' },
  { value: 'sms', label: 'SMS' },
];

const SHOWN = 6;
const GRID = 'tablet:grid-cols-2 phone:grid-cols-1 grid grid-cols-3 gap-[18px]';

type Load =
  | { status: 'loading' }
  | { status: 'error'; error?: ApiError }
  | { status: 'ready'; packs: PackageView[] };

/**
 * The live pack catalog (public, no sign-in). "Buy pack" opens that pack on the portal's packs
 * page, where the purchase and its OTP happen (logging in first when needed).
 */
export function PackShowcase() {
  const router = useRouter();
  const [load, setLoad] = useState<Load>({ status: 'loading' });
  const [filter, setFilter] = useState<Filter>('all');

  const fetchPacks = useCallback(async () => {
    setLoad({ status: 'loading' });
    try {
      setLoad({ status: 'ready', packs: await portalApi.catalog() });
    } catch (error) {
      setLoad({ status: 'error', error: error instanceof ApiError ? error : undefined });
    }
  }, []);

  useEffect(() => {
    void fetchPacks();
  }, [fetchPacks]);

  const shown =
    load.status === 'ready'
      ? load.packs.filter((p) => filter === 'all' || p.kind === filter).slice(0, SHOWN)
      : [];

  return (
    <section id="packs" aria-labelledby="packs-title" className="scroll-mt-24">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="packs-title" className="text-[26px] font-extrabold tracking-[-0.03em]">
            Packs
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            Internet, minutes and SMS at a fixed price. Buy from your balance, bKash or Nagad.
          </p>
        </div>
        <SmallLink href="/portal/packages" className="text-xs">
          See all packs
        </SmallLink>
      </div>

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

      {load.status === 'ready' ? (
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
                pkg={pkg}
                highlighted={false}
                onBuy={() =>
                  router.push(`/portal/packages?highlight=${encodeURIComponent(pkg.code)}`)
                }
              />
            ))}
          </ul>
        )
      ) : load.status === 'error' ? (
        <Panel>
          <LoadError what="The packs" error={load.error} onRetry={() => void fetchPacks()} />
        </Panel>
      ) : (
        <ul className={GRID} aria-hidden="true">
          {Array.from({ length: SHOWN }, (_, i) => (
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
    </section>
  );
}
