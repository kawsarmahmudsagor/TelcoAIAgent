import { cn } from '@/lib/shadcn/utils';

/** The telco. mark: a "T" on the indigo-to-mint gradient tile from the reference UI. */
export function TelcoMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'to-mint from-brand-start grid size-[38px] shrink-0 place-items-center rounded-[13px] bg-linear-135 text-xl font-black text-white shadow-[0_7px_16px_#635bdf44]',
        className
      )}
    >
      T
    </span>
  );
}

/** Mark, wordmark ("telco" with a mint full stop) and the "digital telecom" line. */
export function TelcoBrand({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <TelcoMark />
      <span className="flex flex-col">
        <span className="text-xl leading-tight font-extrabold tracking-[-0.035em]">
          telco<span className="text-mint">.</span>
        </span>
        <span className="text-muted-foreground text-[10px] tracking-[0.16em] uppercase">
          digital telecom
        </span>
      </span>
    </span>
  );
}
