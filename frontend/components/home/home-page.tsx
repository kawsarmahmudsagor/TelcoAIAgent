'use client';

import { AssistantBand } from '@/components/home/assistant-band';
import { HelpTiles } from '@/components/home/help-tiles';
import { Hero } from '@/components/home/hero';
import { PackShowcase } from '@/components/home/pack-showcase';
import { QuickRecharge } from '@/components/home/quick-recharge';
import { SiteFooter } from '@/components/home/site-footer';
import { SiteHeader } from '@/components/home/site-header';
import { useSignedIn } from '@/components/home/use-signed-in';

/**
 * The public home page; the header and hero follow whether a customer is signed in. The assistant
 * bubble comes from the customer layout and works signed out too, as a guest session.
 */
export function HomePage() {
  const me = useSignedIn();
  return (
    <div className="bg-background flex min-h-svh flex-col">
      <SiteHeader me={me} />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-14 px-4 pt-8 pb-10 sm:px-8">
        <Hero me={me} />
        <QuickRecharge />
        <PackShowcase />
        <AssistantBand />
        <HelpTiles />
      </main>
      <SiteFooter />
    </div>
  );
}
