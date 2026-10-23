import { adminNavItemFor } from '@/components/dashboard/shell/nav-items';
import { Panel } from '@/components/portal/ui/panel';

/** Stand-in body for an admin page whose view lands in a later task. */
export function ComingSoon({ href }: { href: string }) {
  const { label, icon: Icon } = adminNavItemFor(href);
  return (
    <>
      <h1 className="phone:text-[23px] mb-5 text-[25px] font-bold tracking-[-0.8px]">{label}</h1>
      <Panel className="text-muted-foreground flex flex-col items-center gap-2 py-14 text-center text-sm">
        <Icon className="size-6" aria-hidden="true" />
        <p>{label} — coming in this release</p>
      </Panel>
    </>
  );
}
