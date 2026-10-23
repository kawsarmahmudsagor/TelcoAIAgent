import { Suspense } from 'react';
import type { Metadata } from 'next';
import { PackageGrid } from '@/components/portal/packages/package-grid';
import { portalNavItemFor } from '@/components/portal/shell/nav-items';

export const metadata: Metadata = { title: portalNavItemFor('/portal/packages').label };

export default function PortalPackagesPage() {
  return (
    <>
      <div className="mb-5">
        <h1 className="phone:text-[23px] mb-[5px] text-[25px] font-bold tracking-[-0.8px]">
          Packages for your lifestyle
        </h1>
        <p className="text-muted-foreground text-xs">
          Pick the right mix of data, minutes and validity. Demo packs are not live carrier offers.
        </p>
      </div>
      {/* PackageGrid reads ?highlight= (useSearchParams needs a Suspense boundary). */}
      <Suspense>
        <PackageGrid />
      </Suspense>
    </>
  );
}
