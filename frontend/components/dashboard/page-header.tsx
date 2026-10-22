import { cn } from '@/lib/shadcn/utils';

interface PageHeaderProps {
  /** The page's one <h1>: the same words as its sidebar entry. */
  title: string;
  description?: React.ReactNode;
  /** The page's main actions, right-aligned (wrapping under the title on a phone). */
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3', className)}>
      <div className="min-w-0">
        <h1 className="font-display text-[1.75rem] leading-tight font-semibold tracking-[-0.02em] sm:text-3xl">
          {title}
        </h1>
        {description && (
          <p className="text-muted-foreground mt-1.5 max-w-[65ch] text-sm">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
