import { cn } from '@/lib/shadcn/utils';

/** The reference's panel: a surface card, 17px radius, hairline border and the soft shadow. */
export function Panel({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'bg-surface border-line rounded-panel shadow-panel phone:p-4 min-w-0 border p-[21px]',
        className
      )}
      {...props}
    />
  );
}

/** A panel's title row: the title and an optional line under it, with an action on the right. */
export function PanelHeader({
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
    <div className={cn('mb-4 flex items-center justify-between gap-2.5', className)}>
      <div className="min-w-0">
        <h3 className="text-sm font-extrabold tracking-[-0.2px]">{title}</h3>
        {description && <p className="text-muted-foreground mt-1 text-[11px]">{description}</p>}
      </div>
      {action}
    </div>
  );
}
