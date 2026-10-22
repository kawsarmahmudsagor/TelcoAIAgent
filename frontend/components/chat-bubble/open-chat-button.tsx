'use client';

import { CHAT_PANEL_ID, useChatBubble } from '@/components/chat-bubble/chat-bubble-context';
import { Button } from '@/components/ui/button';

/** A Button that calls the agent (or shows the call in progress). Takes Button's props. */
export function OpenChatButton({ onClick, ...props }: React.ComponentProps<typeof Button>) {
  const { startCall } = useChatBubble();

  return (
    <Button
      type="button"
      aria-haspopup="dialog"
      aria-controls={CHAT_PANEL_ID}
      {...props}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) startCall();
      }}
    />
  );
}
