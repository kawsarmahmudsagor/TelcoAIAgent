'use client';

import {
  ArrowUpRightIcon,
  MessageSquareTextIcon,
  PhoneIcon,
  SparklesIcon,
  WifiIcon,
} from 'lucide-react';
import { LinkButton, SmallLink } from '@/components/portal/ui/link-button';
import { Panel } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { SectionHead } from '@/components/portal/ui/section-head';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { cn } from '@/lib/shadcn/utils';
import { formatData, formatTaka } from '@/lib/telco-format';
import type { PackageView } from '@/lib/types/portal';

const GRID = 'tablet:grid-cols-2 phone:grid-cols-1 grid grid-cols-3 gap-[18px]';

/** The pack's headline allowance ("20 GB", "300 min", "100 SMS"). */
function headline(pkg: PackageView): string {
  if (pkg.kind === 'voice') return `${pkg.minutes} min`;
  if (pkg.kind === 'sms') return `${pkg.sms} SMS`;
  return formatData(pkg.data_mb);
}

/** "Internet + 200 minutes · 30 days". */
function meta(pkg: PackageView): string {
  const days = pkg.validity_days === 1 ? '1 day' : `${pkg.validity_days} days`;
  const what =
    pkg.kind === 'bundle'
      ? `Internet + ${pkg.minutes} minutes`
      : pkg.kind === 'data'
        ? 'Anytime internet'
        : pkg.kind === 'voice'
          ? 'Any local operator'
          : 'Local SMS';
  return `${what} · ${days}`;
}

const DECO = { data: WifiIcon, bundle: WifiIcon, voice: PhoneIcon, sms: MessageSquareTextIcon };

/** "Made for you": the top three recommended packs, each linking to it in My packages. */
export function MadeForYou() {
  const recs = usePortalQuery('recommendations', portalApi.recommendations);

  return (
    <section aria-labelledby="made-for-you">
      <SectionHead
        title={<span id="made-for-you">Made for you</span>}
        description="Packs that match how you use your phone."
        action={
          <SmallLink href="/portal/offers">
            Explore all offers
            <ArrowUpRightIcon aria-hidden="true" />
          </SmallLink>
        }
      />
      {recs.data ? (
        recs.data.length === 0 ? (
          <Panel className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-muted-foreground text-sm">
              No suggestions yet. They appear once you have some usage.
            </p>
            <LinkButton href="/portal/packages" variant="soft">
              Browse packs
            </LinkButton>
          </Panel>
        ) : (
          <ul className={GRID}>
            {recs.data.slice(0, 3).map(({ package: pkg, reason }, i) => {
              const featured = i === 0;
              const Deco = DECO[pkg.kind];
              return (
                <li
                  key={pkg.code}
                  className={cn(
                    'rounded-metric phone:p-[17px] relative flex min-w-0 flex-col overflow-hidden border p-[18px]',
                    featured
                      ? 'border-[#d8d5ff] bg-linear-145 from-[#e8e8ff] to-[#f7f7ff] text-[#28265d] dark:border-[#3a3775] dark:from-[#2b2a5e] dark:to-[#1c2240] dark:text-[#f2f5ff]'
                      : 'bg-surface border-line'
                  )}
                >
                  <span
                    className={cn(
                      'inline-flex items-center gap-1 self-start rounded-md px-[7px] py-[5px] text-[9px] font-extrabold tracking-[0.7px] uppercase',
                      featured
                        ? 'bg-[#d7d4ff] text-[#3933a2] dark:bg-[#3d3a85] dark:text-[#d9d6ff]'
                        : 'bg-tint-purple text-brand dark:text-[#a9a3ff]'
                    )}
                  >
                    {featured && <SparklesIcon className="size-2.5" aria-hidden="true" />}
                    {featured ? 'For you' : (pkg.tag ?? pkg.kind)}
                  </span>
                  <Deco
                    aria-hidden="true"
                    className="absolute top-[42px] -right-2.5 size-[58px] opacity-[0.09]"
                  />
                  <p className="mt-3.5 mb-0.5 text-[27px] font-black tracking-[-1px]">
                    {headline(pkg)}
                  </p>
                  <p
                    className={cn(
                      'text-[11px]',
                      featured ? 'text-[#66659a] dark:text-[#b8b6e6]' : 'text-muted-foreground'
                    )}
                  >
                    {meta(pkg)}
                  </p>
                  <p
                    className={cn(
                      'mt-2 text-[11px] leading-snug',
                      featured ? 'text-[#66659a] dark:text-[#b8b6e6]' : 'text-muted-foreground'
                    )}
                  >
                    {reason}
                  </p>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-[17px]">
                    <p className="text-sm font-extrabold">{formatTaka(pkg.price)}</p>
                    <LinkButton
                      href={`/portal/packages?highlight=${encodeURIComponent(pkg.code)}`}
                      variant={featured ? 'primary' : 'soft'}
                      aria-label={`Get pack: ${pkg.name}`}
                    >
                      Get pack
                      <ArrowUpRightIcon aria-hidden="true" />
                    </LinkButton>
                  </div>
                </li>
              );
            })}
          </ul>
        )
      ) : recs.error && !recs.loading ? (
        <Panel>
          <LoadError what="Your suggestions" error={recs.error} onRetry={recs.reload} />
        </Panel>
      ) : (
        <ul className={GRID} aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <li
              key={i}
              className="bg-surface border-line rounded-metric flex flex-col gap-3 border p-[18px]"
            >
              <Bone className="h-4 w-16" />
              <Bone className="h-7 w-24" />
              <Bone className="h-3 w-40" />
              <Bone className="mt-3 h-9 w-full" />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
