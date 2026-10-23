import { ArrowUpRightIcon, PlusIcon, ReceiptTextIcon, WalletIcon } from 'lucide-react';
import { LinkButton } from '@/components/portal/ui/link-button';
import { Bone } from '@/components/portal/ui/query-states';
import { formatTaka } from '@/lib/telco-format';
import type { AccountSummary } from '@/lib/types/portal';

const HERO =
  'relative isolate overflow-hidden rounded-hero bg-linear-[115deg] from-[#37328d] via-[#5148ce] via-53% to-[#6d68ee] px-[27px] py-[25px] text-white shadow-[0_14px_28px_#4d46be22] min-h-[225px] tablet:p-[22px] phone:min-h-[215px]';

/** The indigo balance card: main balance (prepaid) or the bill due (postpaid), and the next steps. */
export function BalanceHero({ summary }: { summary: AccountSummary }) {
  const postpaid = summary.plan_type === 'postpaid';
  const amount = postpaid ? summary.postpaid_due : summary.main_balance;
  // The symbol is set smaller beside the figure, as in the reference.
  const figure = formatTaka(amount).replace('৳', '').trim();

  return (
    <div className={HERO}>
      <HeroRings />
      <span
        aria-hidden="true"
        className="tablet:right-3.5 tablet:opacity-45 phone:right-[17px] phone:bottom-7 phone:size-[82px] phone:[&_svg]:size-[38px] absolute right-[35px] bottom-[23px] z-[1] grid size-[115px] place-items-center rounded-full border border-white/[0.13] bg-white/[0.04] [&_svg]:size-[54px] [&_svg]:drop-shadow-[0_7px_10px_#27227466]"
      >
        {postpaid ? <ReceiptTextIcon strokeWidth={1.5} /> : <WalletIcon strokeWidth={1.5} />}
      </span>

      <div className="relative z-[2]">
        <p className="flex flex-wrap items-center gap-[9px] text-xs font-semibold text-[#dfdeff]">
          <span
            aria-hidden="true"
            className="size-[7px] rounded-full bg-[#55e4c5] shadow-[0_0_0_4px_#55e4c522]"
          />
          {postpaid ? 'POSTPAID ACCOUNT' : 'PREPAID ACCOUNT'}
          <span aria-hidden="true" className="opacity-50">
            ·
          </span>
          <span>{summary.masked_msisdn}</span>
        </p>
        <p className="phone:text-[35px] mt-[17px] mb-0.5 text-[39px] leading-tight font-[850] tracking-[-1.6px]">
          <span className="text-[17px] font-semibold tracking-normal">৳</span> {figure}
        </p>
        <p className="text-xs text-[#d5d4ff]">
          {postpaid ? 'Bill due this cycle' : 'Available main balance'}
        </p>
        <div className="narrow:[&_a]:px-2.5 narrow:[&_a]:py-[9px] mt-[23px] flex flex-wrap gap-2.5">
          <LinkButton href="/portal/recharge" variant="white">
            <PlusIcon aria-hidden="true" />
            {postpaid ? 'Pay bill' : 'Recharge now'}
          </LinkButton>
          <LinkButton href="/portal/balance" variant="glass">
            View details
            <ArrowUpRightIcon aria-hidden="true" />
          </LinkButton>
        </div>
      </div>
    </div>
  );
}

/** The reference's decorative circles in the hero's corners. */
function HeroRings() {
  return (
    <>
      <span
        aria-hidden="true"
        className="absolute -top-[112px] -right-[58px] size-[270px] rounded-full border border-white/[0.125] shadow-[0_0_0_28px_#ffffff08,0_0_0_57px_#ffffff06]"
      />
      <span
        aria-hidden="true"
        className="absolute right-[35px] -bottom-[91px] size-[135px] rounded-full bg-white/[0.06]"
      />
    </>
  );
}

/** The hero's shape while the summary loads. */
export function BalanceHeroSkeleton() {
  return (
    <div className={HERO} aria-hidden="true">
      <HeroRings />
      <div className="relative z-[2] flex flex-col gap-4">
        <Bone className="h-3 w-48 bg-white/20" />
        <Bone className="mt-2 h-10 w-44 bg-white/20" />
        <Bone className="h-3 w-36 bg-white/20" />
        <div className="mt-3 flex gap-2.5">
          <Bone className="h-9 w-32 bg-white/20" />
          <Bone className="h-9 w-28 bg-white/20" />
        </div>
      </div>
    </div>
  );
}
