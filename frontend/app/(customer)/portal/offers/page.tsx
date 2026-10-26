import type { Metadata } from 'next';
import { OffersView } from '@/components/portal/offers/offers-view';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';

const { label } = portalNavItemFor('/portal/offers');

export const metadata: Metadata = { title: label };

export default function PortalOffersPage() {
  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] mb-[5px] text-[25px] font-bold tracking-[-0.8px]">
          {label}
        </h1>
        <p className="text-muted-foreground text-xs">
          Special deals and little extras, picked around your usage.
        </p>
      </div>
      <OffersView />
    </>
  );
}
