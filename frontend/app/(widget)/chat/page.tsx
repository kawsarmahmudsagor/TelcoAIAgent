import { Suspense } from 'react';
import { headers } from 'next/headers';
import { App } from '@/components/app/app';
import { getAppConfig } from '@/lib/utils';

/**
 * The standalone voice/chat page. Without `?room=` it starts a new conversation (the agent is
 * dispatched when the user presses Start); with `?room=<name>` it joins that room straight away
 * -- an answered scheduled cold call (app/dashboard/incoming).
 */
export default async function ChatPage() {
  const appConfig = await getAppConfig(await headers());

  return (
    <Suspense>
      <App appConfig={appConfig} />
    </Suspense>
  );
}
