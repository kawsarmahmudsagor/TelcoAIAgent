import { cn } from '@/lib/shadcn/utils';

/** A titled panel on a page with several of them (Overview, Chatbot tabs): heading row with an
 * optional action on the right, then the body. Flat card, hairline border (see DESIGN.md). */
export function SectionCard({
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
  headingLevel = 2,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  headingLevel?: 2 | 3;
}) {
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <section className={cn('bg-card flex min-w-0 flex-col rounded-lg border', className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-4 sm:px-5 sm:pt-5">
        <div className="min-w-0">
          <Heading className="text-base font-semibold">{title}</Heading>
          {description && (
            <p className="text-muted-foreground mt-1 max-w-[65ch] text-sm">{description}</p>
          )}
        </div>
        {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
      </div>
      <div className={cn('flex-1 px-4 pt-4 pb-4 sm:px-5 sm:pb-5', bodyClassName)}>{children}</div>
    </section>
  );
}
