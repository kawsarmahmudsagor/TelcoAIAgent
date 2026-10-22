'use client';

import { useState } from 'react';
import {
  Loader2Icon,
  Maximize2Icon,
  Minimize2Icon,
  MinusIcon,
  PhoneIcon,
  XIcon,
} from 'lucide-react';
import type { AppConfig } from '@/app-config';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { AppSetup } from '@/components/app/app';
import { CallAudioProvider } from '@/components/app/call/call-audio-provider';
import { ViewController } from '@/components/app/view-controller';
import { CHAT_PANEL_ID, useChatBubble } from '@/components/chat-bubble/chat-bubble-context';
import {
  ConversationHistoryMenu,
  PastConversationView,
} from '@/components/chat-bubble/conversation-history';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';
import type { VisitorConversationSummary } from '@/lib/types';
import { getStyles } from '@/lib/utils';

/**
 * The public site's agent: a launcher fixed to the bottom-right corner and the chat panel it
 * opens (a full-screen sheet below `sm`). Rendered once by the (site) layout and always mounted:
 * closing the panel only hides it, so the session, its audio and the transcript/text-stream
 * hooks inside the session view (one handler per topic) are never torn down or registered twice.
 * For the same reason an earlier conversation from the history is shown *over* the session view,
 * which stays mounted (just invisible) underneath.
 */
export function ChatBubble({ appConfig }: { appConfig: AppConfig }) {
  const {
    session,
    isOpen,
    isConnected,
    open,
    startCall,
    autoConnecting,
    close,
    isFullscreen,
    toggleFullscreen,
    exitFullscreen,
    visitorId,
  } = useChatBubble();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [viewing, setViewing] = useState<VisitorConversationSummary | null>(null);
  const styles = getStyles(appConfig, 'panel');
  // The live session's room, left out of the history (it's the conversation on screen).
  const currentRoom = isConnected ? session.room.name || undefined : undefined;

  return (
    <CallAudioProvider session={session}>
      <AppSetup />

      <div
        id={CHAT_PANEL_ID}
        role="dialog"
        aria-label={`Chat with the ${appConfig.companyName} assistant`}
        // Scopes the widget's neutral tokens and accent (styles/globals.css) to the panel.
        data-surface="widget-panel"
        data-fullscreen={isFullscreen || undefined}
        inert={!isOpen}
        onKeyDown={(event) => {
          // (The history dropdown closes itself on Escape and stops it reaching here.)
          if (event.key !== 'Escape') return;
          if (viewing) setViewing(null);
          else if (isFullscreen) exitFullscreen();
          else close();
        }}
        className={cn(
          'bg-background text-foreground fixed inset-0 z-50 flex flex-col overflow-hidden',
          // From `sm` up, both sizes are anchored bottom-right with explicit right/bottom/width/
          // height (and top/left auto), so going fullscreen and back is a plain CSS transition of
          // the panel's box -- the content reflows in place, nothing remounts or scales.
          'sm:inset-auto',
          'sm:transition-[right,bottom,width,height,border-radius,box-shadow] sm:duration-300 sm:ease-[cubic-bezier(0.32,0.72,0,1)] sm:motion-reduce:transition-none',
          isFullscreen
            ? 'sm:right-0 sm:bottom-0 sm:h-full sm:w-full sm:rounded-none sm:border-0 sm:shadow-none'
            : 'sm:right-4 sm:bottom-20 sm:h-[min(640px,80svh)] sm:w-[min(400px,calc(100vw-2rem))] sm:rounded-xl sm:border sm:shadow-2xl',
          !isOpen && 'hidden'
        )}
      >
        {styles && <style>{styles}</style>}
        <header className="flex h-12 shrink-0 items-center gap-2 border-b pr-2 pl-4">
          <span className="truncate text-sm font-semibold">{appConfig.companyName} assistant</span>
          {isConnected && (
            <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
              <span aria-hidden="true" className="size-2 rounded-full bg-emerald-500" />
              Live
            </span>
          )}
          <span className="flex-1" />
          <StartAudioButton label="Allow audio" size="sm" />
          {visitorId && (
            <ConversationHistoryMenu
              visitorId={visitorId}
              currentRoom={currentRoom}
              isConnected={isConnected}
              open={historyOpen}
              onOpenChange={setHistoryOpen}
              onSelect={(conversation) => {
                setHistoryOpen(false);
                setViewing(conversation);
              }}
              onShowCurrent={() => {
                setHistoryOpen(false);
                setViewing(null);
              }}
            />
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={toggleFullscreen}
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Expand chat to fullscreen'}
            title={isFullscreen ? 'Exit fullscreen' : 'Expand chat to fullscreen'}
            // Below `sm` the panel is always a full-screen sheet; a call is always fullscreen.
            className={cn('max-sm:hidden', isConnected && 'hidden')}
          >
            {isFullscreen ? (
              <Minimize2Icon aria-hidden="true" />
            ) : (
              <Maximize2Icon aria-hidden="true" />
            )}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={close}
            aria-label="Minimise chat"
            title={isConnected ? 'Minimise (the call keeps going)' : 'Minimise'}
          >
            <MinusIcon aria-hidden="true" />
          </Button>
        </header>
        <div className="relative min-h-0 flex-1">
          {/* Never unmounted: hidden (and inert) while an earlier conversation is on top. */}
          <div className={cn('absolute inset-0', viewing && 'invisible')} inert={Boolean(viewing)}>
            <ViewController appConfig={appConfig} variant="panel" autoConnecting={autoConnecting} />
          </div>
          {viewing && visitorId && (
            <PastConversationView
              // A fresh view (and fetch) per conversation.
              key={viewing.id}
              visitorId={visitorId}
              summary={viewing}
              onBack={() => setViewing(null)}
              className="absolute inset-0 z-10"
            />
          )}
        </div>
      </div>

      <Button
        type="button"
        // Pressing the phone starts the call at once; during a call it just reopens the panel.
        onClick={isOpen ? close : isConnected ? open : startCall}
        disabled={autoConnecting}
        aria-busy={autoConnecting || undefined}
        aria-expanded={isOpen}
        aria-controls={CHAT_PANEL_ID}
        aria-label={
          isOpen
            ? 'Close chat'
            : isConnected
              ? 'Open chat (call in progress)'
              : autoConnecting
                ? 'Connecting the call'
                : 'Call our AI agent'
        }
        className={cn(
          'fixed right-4 bottom-4 z-50 size-14 rounded-full shadow-lg',
          // The open panel is a full-screen sheet on phones; it has its own minimise button.
          isOpen && 'max-sm:hidden',
          // During a call the open panel is fullscreen, and the call's own chat bubble takes this
          // corner; the header's minimise button closes it.
          isOpen && isConnected && 'hidden'
        )}
      >
        {isOpen ? (
          <XIcon aria-hidden="true" className="size-6" />
        ) : autoConnecting ? (
          <Loader2Icon aria-hidden="true" className="size-6 animate-spin" />
        ) : (
          <PhoneIcon aria-hidden="true" className="size-6" />
        )}
        {isConnected && !isOpen && (
          <span
            aria-hidden="true"
            className="ring-background absolute top-0.5 right-0.5 size-3.5 rounded-full bg-emerald-500 ring-2"
          />
        )}
      </Button>
    </CallAudioProvider>
  );
}
