import type { Metadata } from 'next';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';
import { Panel } from '@/components/portal/ui/panel';

const { label } = portalNavItemFor('/portal/support');

export const metadata: Metadata = { title: label };

/** Placeholder until a later Phase 3 task builds this page. */
export default function PortalSupportPage() {
  return (
    <>
      <h1 className="phone:text-[23px] mb-5 text-[25px] font-bold tracking-[-0.8px]">{label}</h1>
      <Panel>
        <p className="font-semibold">Coming soon</p>
        <p className="text-muted-foreground mt-1 text-sm">This page is on its way.</p>
      </Panel>
    </>
  );
}
