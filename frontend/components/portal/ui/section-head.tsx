import { cn } from '@/lib/shadcn/utils';

/** A section's heading between panels: title, an optional muted line, and an action on the right. */
export function SectionHead({
  title,
  description,
  action,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'phone:mt-[22px] mt-[25px] mb-3.5 flex items-center justify-between gap-3',
        className
      )}
    >
      <div className="min-w-0">
        <h2 className="text-base font-bold tracking-[-0.3px]">{title}</h2>
        {description && <p className="text-muted-foreground mt-1 text-[11px]">{description}</p>}
      </div>
      {action}
    </div>
  );
}
