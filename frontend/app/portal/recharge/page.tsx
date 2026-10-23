import type { Metadata } from 'next';
import { SparklesIcon } from 'lucide-react';
import { RecentRecharges } from '@/components/portal/recharge/recent-recharges';
import { RechargeForm } from '@/components/portal/recharge/recharge-form';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';
import { LinkButton } from '@/components/portal/ui/link-button';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';

const { label } = portalNavItemFor('/portal/recharge');

export const metadata: Metadata = { title: label };

const HELP_PROMPT = 'My recharge was successful but my balance did not update.';

export default function PortalRechargePage() {
  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] mb-[5px] text-[25px] font-bold tracking-[-0.8px]">
          {label}
        </h1>
        <p className="text-muted-foreground text-xs">
          Top up your balance or pay a postpaid bill in a few simple steps.
        </p>
      </div>

      <div className="phone:grid-cols-1 grid grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)] items-start gap-[18px]">
        <RechargeForm />
        <div className="flex min-w-0 flex-col gap-[18px]">
          <RecentRecharges />
          <Panel>
            <PanelHeader
              title="Need help with a recharge?"
              description="If your balance wasn’t updated after a successful payment, telco. AI can check the transaction for you."
              className="mb-0"
            />
            <LinkButton
              href={`/portal/assistant?q=${encodeURIComponent(HELP_PROMPT)}`}
              variant="soft"
              className="mt-[13px]"
            >
              <SparklesIcon aria-hidden="true" />
              Troubleshoot a recharge
            </LinkButton>
          </Panel>
        </div>
      </div>
    </>
  );
}
