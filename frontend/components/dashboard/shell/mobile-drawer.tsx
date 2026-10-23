'use client';

import { SidebarContent } from '@/components/dashboard/shell/sidebar';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';

/**
 * At 760px and below the side column becomes a 260px off-canvas drawer, opened by the topbar's
 * menu button. Following a link closes it.
 */
export function MobileDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="left"
        aria-describedby={undefined}
        className="bg-surface border-line w-[260px] gap-0 overflow-y-auto p-0 shadow-[15px_0_45px_#0002] sm:max-w-[260px]"
      >
        <SheetTitle className="sr-only">Menu</SheetTitle>
        <SidebarContent onNavigate={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  );
}
