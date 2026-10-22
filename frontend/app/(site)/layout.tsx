import { headers } from 'next/headers';
import { ChatBubble } from '@/components/chat-bubble/chat-bubble';
import { ChatBubbleProvider } from '@/components/chat-bubble/chat-bubble-context';
import { Toaster } from '@/components/ui/sonner';
import { getAppConfig } from '@/lib/utils';

/**
 * The public site (/home and the pages beside it). The ChatBubble renders as a sibling of the
 * page, never around it, and the provider is a plain context wrapper, so client navigation
 * between public pages keeps one call running. not-found/error/loading live in this segment so a
 * 404 or a crash replaces only the page, not this layout (which would end the call). Leaving
 * (site), for /login or /dashboard, ends it.
 */
export default async function SiteLayout({ children }: { children: React.ReactNode }) {
  const appConfig = await getAppConfig(await headers());

  return (
    <ChatBubbleProvider appConfig={appConfig}>
      {children}
      <ChatBubble appConfig={appConfig} />
      {/* Top-center: the bottom-right corner belongs to the bubble. */}
      <Toaster position="top-center" />
    </ChatBubbleProvider>
  );
}
