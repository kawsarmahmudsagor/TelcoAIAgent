'use client';

import { PackageIcon, SparklesIcon } from 'lucide-react';
import { packageContents, validity } from '@/components/portal/packages/package-card';
import { PortalButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';
import { formatTaka } from '@/lib/telco-format';
import type { TelcoPackage, TelcoPackagesPayload } from '@/lib/telco-topics';

/** What "Buy" says to the agent, so it runs purchase_package and sends its own confirm card. */
export const buyMessage = (pkg: TelcoPackage) => `I want to buy ${pkg.name} (${pkg.code})`;

/**
 * The packages the agent found or recommends, as a horizontal row of compact cards. "Buy" asks
 * the agent in the chat (it does not call the portal API): the purchase then runs through the
 * agent's confirm card.
 */
export function PackageCards({
  data,
  onBuy,
}: {
  data: TelcoPackagesPayload;
  onBuy(pkg: TelcoPackage): void;
}) {
  const anyTag = data.packages.some((p) => p.tag);
  return (
    <section aria-label={data.title} className="w-full min-w-0">
      <p className="text-muted-foreground mb-2 flex items-center gap-1.5 text-[11px] font-bold">
        <PackageIcon className="size-3.5" aria-hidden="true" />
        {data.title}
        <span className="font-medium">· {data.packages.length}</span>
      </p>
      {/* Untagged cards keep the tag's space, so the names line up across the row. */}
      <ul
        className={cn(
          '-mx-1 flex snap-x snap-mandatory gap-2.5 overflow-x-auto overscroll-x-contain px-1 pb-2',
          '[scrollbar-width:thin]'
        )}
      >
        {data.packages.map((pkg) => {
          const featured = pkg.tag?.toUpperCase() === 'POPULAR';
          return (
            <li
              key={pkg.code}
              className={cn(
                'rounded-metric flex w-[188px] shrink-0 snap-start flex-col border p-3.5',
                featured
                  ? 'border-[#d8d5ff] bg-linear-145 from-[#e8e8ff] to-[#f7f7ff] text-[#28265d] dark:border-[#3a3775] dark:from-[#2b2a5e] dark:to-[#1c2240] dark:text-[#f2f5ff]'
                  : 'bg-surface border-line'
              )}
            >
              {pkg.tag ? (
                <span
                  className={cn(
                    'mb-2 inline-flex items-center gap-1 self-start rounded-md px-1.5 py-[3px] text-[9px] font-extrabold tracking-[0.6px] uppercase',
                    featured
                      ? 'bg-[#d7d4ff] text-[#3933a2] dark:bg-[#3d3a85] dark:text-[#d9d6ff]'
                      : 'bg-tint-purple text-brand dark:text-[#a9a3ff]'
                  )}
                >
                  {featured && <SparklesIcon className="size-2.5" aria-hidden="true" />}
                  {pkg.tag}
                </span>
              ) : (
                anyTag && <span aria-hidden="true" className="mb-2 h-[19px]" />
              )}
              <h4 className="text-sm leading-tight font-extrabold tracking-[-0.3px]">{pkg.name}</h4>
              <p
                className={cn(
                  'mt-1 text-[11px] leading-snug',
                  featured ? 'text-[#66659a] dark:text-[#b8b6e6]' : 'text-muted-foreground'
                )}
              >
                {packageContents(pkg)} · {validity(pkg.validity_days)}
              </p>
              <div className="mt-auto flex items-center justify-between gap-2 pt-3">
                <p className="text-[13px] font-extrabold tabular-nums">{formatTaka(pkg.price)}</p>
                <PortalButton
                  variant={featured ? 'primary' : 'soft'}
                  onClick={() => onBuy(pkg)}
                  aria-label={`Buy ${pkg.name}`}
                  className="min-h-8 px-3 py-2"
                >
                  Buy
                </PortalButton>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
