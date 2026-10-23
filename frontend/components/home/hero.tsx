import { LayoutDashboardIcon, LogInIcon, SparklesIcon } from 'lucide-react';
import type { SignedIn } from '@/components/home/use-signed-in';
import { LinkButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';

type Line = { from: 'customer' | 'ai'; text: string; lang?: 'bn' };

// What a real chat with the assistant looks like: Bangla, then English, ending in the OTP step.
const CHAT: Line[] = [
  { from: 'customer', text: 'আমার ব্যালেন্স কত?', lang: 'bn' },
  {
    from: 'ai',
    text: 'আপনার মূল ব্যালেন্স ৳ 486.50। আপনার 8 GB প্যাকের মেয়াদ ৩ দিনের মধ্যে শেষ হবে।',
    lang: 'bn',
  },
  { from: 'customer', text: 'Renew it for me.' },
  { from: 'ai', text: 'I’ve sent a code to your phone. Enter it to renew the pack for ৳ 299.' },
];

/** The indigo hero: what My telco. does, the account action, and a sample assistant chat. */
export function Hero({ me }: { me: SignedIn }) {
  return (
    <section
      aria-labelledby="home-title"
      className="rounded-hero from-hero-from via-hero-via to-hero-to phone:px-5 phone:py-8 relative isolate overflow-hidden bg-linear-[115deg] via-53% px-10 py-12 text-white shadow-[0_14px_28px_#4d46be22]"
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 -left-24 -z-10 size-[340px] rounded-full border border-white/10 shadow-[0_0_0_34px_#ffffff07,0_0_0_70px_#ffffff05]"
      />
      <div className="tablet:grid-cols-1 grid grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] items-center gap-10">
        <div className="max-w-xl">
          <h1
            id="home-title"
            className="phone:text-[34px] text-[46px] leading-[1.05] font-extrabold tracking-[-0.035em] text-balance"
          >
            Everything on your number, in one place.
          </h1>
          <p className="text-hero-muted mt-5 max-w-[52ch] text-base leading-relaxed">
            Check your balance, recharge, buy a pack or raise a complaint. Telco AI answers in
            Bangla or English, by chat or voice.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {me ? (
              <LinkButton href="/portal" variant="white" className="min-h-11 px-5 text-sm">
                <LayoutDashboardIcon aria-hidden="true" />
                Open my dashboard
              </LinkButton>
            ) : (
              <LinkButton href="/signin" variant="white" className="min-h-11 px-5 text-sm">
                <LogInIcon aria-hidden="true" />
                Log in to My telco.
              </LinkButton>
            )}
            <LinkButton href="#packs" variant="glass" className="min-h-11 px-5 text-sm">
              See packs
            </LinkButton>
          </div>
        </div>

        <figure className="tablet:max-w-lg w-full justify-self-end rounded-[18px] border border-white/15 bg-white/[0.07] p-4 backdrop-blur-sm">
          <figcaption className="text-hero-soft mb-3 flex items-center gap-2 text-xs font-semibold">
            <span aria-hidden="true" className="bg-hero-dot size-2 rounded-full" />A chat with Telco
            AI
          </figcaption>
          <ol className="flex flex-col gap-2.5">
            {CHAT.map((line, i) => (
              <li
                key={i}
                lang={line.lang}
                style={{ animationDelay: `${300 + i * 650}ms` }}
                className={cn(
                  'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-snug motion-safe:animate-[home-rise_420ms_ease-out_both]',
                  line.from === 'customer'
                    ? 'text-promo-ink self-end rounded-br-md bg-white font-semibold'
                    : 'self-start rounded-bl-md bg-white/15 text-white'
                )}
              >
                {line.from === 'customer' && <span className="sr-only">Customer: </span>}
                {line.from === 'ai' && (
                  <span className="text-hero-soft mb-1 flex items-center gap-1 text-[11px] font-bold">
                    <SparklesIcon aria-hidden="true" className="size-3" />
                    Telco AI
                  </span>
                )}
                {line.text}
              </li>
            ))}
          </ol>
        </figure>
      </div>
    </section>
  );
}
