import { Loader2Icon, PhoneIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

// Radii of the arcs that rise off the sun, innermost first. The sun sits at (18, 22) with r=9,
// as in BrandMark.
const ARC_RADII = [13, 17.5, 22];

/**
 * The Horizon mark with its sun broadcasting: brass arcs pulse outward from the horizon, behind
 * the towers. The pulse quickens while a call connects. Decorative only.
 */
function HorizonCallMark({ connecting }: { connecting: boolean }) {
  return (
    <svg viewBox="-6 -2 48 28" aria-hidden="true" className="text-foreground mb-7 h-auto w-40">
      {ARC_RADII.map((r, i) => (
        <path
          key={r}
          d={`M${18 - r} 22A${r} ${r} 0 0 1 ${18 + r} 22`}
          fill="none"
          strokeWidth="1.1"
          strokeLinecap="round"
          className="stroke-brass opacity-40 motion-safe:animate-[horizon-wave_var(--wave-duration)_ease-in-out_infinite]"
          style={
            {
              '--wave-duration': connecting ? '1.2s' : '2.6s',
              animationDelay: `${i * (connecting ? 0.2 : 0.45)}s`,
            } as React.CSSProperties
          }
        />
      ))}
      <path d="M9 22a9 9 0 0 1 18 0Z" className="fill-brass" />
      <rect x="4" y="12" width="4" height="10" rx="0.5" fill="currentColor" />
      <rect x="9.5" y="7" width="4.5" height="15" rx="0.5" fill="currentColor" />
      <rect x="-2" y="22" width="40" height="2" rx="1" fill="currentColor" />
    </svg>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
  /** A connect is under way: the button is disabled and says so. */
  connecting?: boolean;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  connecting = false,
  ref,
  className,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  return (
    <div ref={ref} className={cn(className)}>
      <section className="bg-background flex flex-col items-center px-2 text-center">
        <HorizonCallMark connecting={connecting} />

        <h1 className="font-display text-foreground text-[1.75rem] leading-tight font-semibold tracking-[-0.02em] text-balance">
          Horizon Realty
        </h1>
        <p className="text-muted-foreground mt-2 max-w-[30ch] text-[0.9375rem] leading-relaxed text-pretty">
          Ask about flats to rent or buy, prices by area, or book a viewing.
        </p>

        <Button
          size="lg"
          onClick={onStartCall}
          disabled={connecting}
          aria-busy={connecting}
          className="mt-8 h-12 min-w-56 gap-2.5 rounded-full px-7 text-[0.9375rem] font-semibold shadow-md transition-[transform,box-shadow] hover:shadow-lg active:scale-[0.98] motion-reduce:transition-none"
        >
          {connecting ? (
            <Loader2Icon aria-hidden="true" className="size-[18px] animate-spin" />
          ) : (
            <PhoneIcon aria-hidden="true" className="size-[18px]" />
          )}
          {connecting ? 'Connecting…' : startButtonText}
        </Button>
      </section>
    </div>
  );
};
