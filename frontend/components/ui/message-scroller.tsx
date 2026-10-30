'use client';

import * as React from 'react';
import { ArrowDownIcon } from 'lucide-react';
import {
  MessageScroller as MessageScrollerPrimitive,
  useMessageScroller,
  useMessageScrollerScrollable,
  useMessageScrollerVisibility,
} from '@shadcn/react/message-scroller';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

function MessageScrollerProvider(
  props: React.ComponentProps<typeof MessageScrollerPrimitive.Provider>
) {
  return <MessageScrollerPrimitive.Provider {...props} />;
}

function MessageScroller({
  className,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Root>) {
  return (
    <MessageScrollerPrimitive.Root
      data-slot="message-scroller"
      className={cn(
        'group/message-scroller relative flex size-full min-h-0 flex-col overflow-hidden',
        className
      )}
      {...props}
    />
  );
}

// The primitive's scrollEdgeThreshold default.
const END_THRESHOLD = 8;

function MessageScrollerViewport({
  className,
  onWheel,
  onTouchEnd,
  onKeyDown,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Viewport>) {
  const { scrollToEnd } = useMessageScroller();
  const timerRef = React.useRef<number | null>(null);
  React.useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    []
  );

  // Any wheel, touch move or scroll key inside the viewport stops auto-follow, and only a
  // real vertical scroll event turns it back on. A gesture that never scrolls the viewport
  // -- swiping a horizontal card carousel, or wheeling down when already at the bottom --
  // left it off for good, so later messages landed below the fold. If the view didn't move
  // and still sits at the bottom, pin it again.
  const repinIfStill = (el: HTMLElement) => {
    const before = el.scrollTop;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      const atEnd = el.scrollHeight - el.scrollTop - el.clientHeight <= END_THRESHOLD;
      if (el.isConnected && el.scrollTop === before && atEnd) scrollToEnd();
    }, 150);
  };

  return (
    <MessageScrollerPrimitive.Viewport
      data-slot="message-scroller-viewport"
      onWheel={(e) => {
        repinIfStill(e.currentTarget);
        onWheel?.(e);
      }}
      onTouchEnd={(e) => {
        repinIfStill(e.currentTarget);
        onTouchEnd?.(e);
      }}
      onKeyDown={(e) => {
        repinIfStill(e.currentTarget);
        onKeyDown?.(e);
      }}
      className={cn(
        // Hide the thumb while auto-scrolling by colouring it transparent, not
        // with scrollbar-width:none -- that also drops the stable gutter, so the
        // content width flips by a scrollbar's width on every streamed chunk.
        // Bubbles shift sideways, text rewraps, the height changes, and that
        // triggers another auto-scroll: a jitter loop that runs until the reply
        // stops streaming.
        'scroll-fade-b size-full min-h-0 min-w-0 scrollbar-thin scrollbar-gutter-stable overflow-y-auto overscroll-contain contain-content data-autoscrolling:[scrollbar-color:transparent_transparent]',
        className
      )}
      {...props}
    />
  );
}

function MessageScrollerContent({
  className,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Content>) {
  return (
    <MessageScrollerPrimitive.Content
      data-slot="message-scroller-content"
      className={cn('flex h-max min-h-full flex-col gap-8', className)}
      {...props}
    />
  );
}

function MessageScrollerItem({
  className,
  scrollAnchor = false,
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Item>) {
  return (
    <MessageScrollerPrimitive.Item
      data-slot="message-scroller-item"
      scrollAnchor={scrollAnchor}
      className={cn(
        'min-w-0 shrink-0 [contain-intrinsic-size:auto_10rem] [content-visibility:auto]',
        className
      )}
      {...props}
    />
  );
}

function MessageScrollerButton({
  direction = 'end',
  className,
  children,
  render,
  variant = 'secondary',
  size = 'icon-sm',
  ...props
}: React.ComponentProps<typeof MessageScrollerPrimitive.Button> &
  Pick<React.ComponentProps<typeof Button>, 'variant' | 'size'>) {
  return (
    <MessageScrollerPrimitive.Button
      data-slot="message-scroller-button"
      data-direction={direction}
      data-variant={variant}
      data-size={size}
      direction={direction}
      className={cn(
        'border-border bg-background text-foreground hover:bg-muted hover:text-foreground absolute inset-s-1/2 -translate-x-1/2 transition-[translate,scale,opacity] duration-200 data-[active=false]:pointer-events-none data-[active=false]:scale-95 data-[active=false]:opacity-0 data-[active=false]:duration-400 data-[active=false]:ease-[cubic-bezier(0.7,0,0.84,0)] data-[active=true]:translate-y-0 data-[active=true]:scale-100 data-[active=true]:opacity-100 data-[active=true]:ease-[cubic-bezier(0.23,1,0.32,1)] data-[direction=end]:bottom-4 data-[direction=end]:data-[active=false]:translate-y-full data-[direction=start]:top-4 data-[direction=start]:data-[active=false]:-translate-y-full rtl:translate-x-1/2 data-[direction=start]:[&_svg]:rotate-180',
        className
      )}
      render={render ?? <Button variant={variant} size={size} />}
      {...props}
    >
      {children ?? (
        <>
          <ArrowDownIcon />
          <span className="sr-only">
            {direction === 'end' ? 'Scroll to end' : 'Scroll to start'}
          </span>
        </>
      )}
    </MessageScrollerPrimitive.Button>
  );
}

export {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
  useMessageScroller,
  useMessageScrollerScrollable,
  useMessageScrollerVisibility,
};
