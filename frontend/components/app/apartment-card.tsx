'use client';

import Link from 'next/link';
import { BedDoubleIcon, MapPinIcon, ShowerHeadIcon, SquareIcon } from 'lucide-react';
import { motion } from 'motion/react';
import { useOptionalChatBubble } from '@/components/chat-bubble/chat-bubble-context';
import { OfferBadge } from '@/components/offers/offer-badge';
import type { ApartmentCardData } from '@/lib/livekit-text-streams';
import { cn } from '@/lib/shadcn/utils';

const MotionLink = motion.create(Link);
// Below Tailwind's `sm`, where the open chat panel is a full-screen sheet over the page.
const SHEET_QUERY = '(max-width: 639.98px)';

const MAX_VISIBLE_AMENITIES = 2;
const PLACEHOLDER_IMAGE = '/listings/placeholder.jpg';

// Delay is deliberately large enough to read as items landing one at a time
// (rather than a single quick group fade), since this plays out while the
// agent is talking through the results.
const STAGGER_SECONDS = 0.12;

const cardVariants = {
  hidden: { opacity: 0, y: 10, scale: 0.98 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.32, delay: index * STAGGER_SECONDS, ease: [0.16, 1, 0.3, 1] },
  }),
  exit: { opacity: 0, scale: 0.98, transition: { duration: 0.15, ease: 'easeIn' } },
};

function formatAmenity(amenity: string) {
  return amenity
    .split('_')
    .map((word) => word[0]?.toUpperCase() + word.slice(1))
    .join(' ');
}

export function ApartmentCard({ card, index = 0 }: { card: ApartmentCardData; index?: number }) {
  const isRent = card.listing_type === 'rent';
  const priceLabel = `৳${card.price.toLocaleString()}`;
  const visibleAmenities = card.amenities.slice(0, MAX_VISIBLE_AMENITIES);
  const hiddenAmenityCount = card.amenities.length - visibleAmenities.length;
  // On the public site the bubble outlives navigation, so the page opens in place: a phone's
  // full-screen sheet gets out of the way, and a fullscreen panel animates back to its docked
  // size so the listing shows behind it. Elsewhere (the dashboard's call page) leaving the page
  // would end the call, so it opens in a new tab.
  const bubble = useOptionalChatBubble();

  return (
    <MotionLink
      href={`/properties/${card.id}`}
      {...(bubble ? {} : { target: '_blank', rel: 'noopener' })}
      onClick={() => {
        if (!bubble) return;
        if (window.matchMedia(SHEET_QUERY).matches) bubble.close();
        else if (bubble.isFullscreen) bubble.exitFullscreen();
      }}
      custom={index}
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="group hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:ring-ring/50 flex items-center gap-3 px-3 py-2.5 transition-colors duration-200 outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
    >
      <div className="bg-muted relative size-20 shrink-0 overflow-hidden rounded-xl">
        {/* Plain <img>: listing photos can come from any host an admin pastes. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={card.image_url || PLACEHOLDER_IMAGE}
          alt={card.title}
          onError={(event) => {
            const img = event.currentTarget;
            // Guard against a loop if the placeholder itself fails.
            if (!img.src.endsWith(PLACEHOLDER_IMAGE)) img.src = PLACEHOLDER_IMAGE;
          }}
          className="size-full object-cover transition-transform duration-500 ease-out group-hover:scale-110"
        />
        <span
          className={cn(
            'absolute top-1 left-1 rounded-full px-1.5 py-[1px] text-[9px] font-semibold tracking-wide uppercase backdrop-blur-md',
            isRent ? 'bg-emerald-500/90 text-white' : 'bg-violet-500/90 text-white'
          )}
        >
          {isRent ? 'Rent' : 'Sale'}
        </span>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-start justify-between gap-2">
          <p className="min-w-0 truncate text-sm leading-tight font-semibold underline-offset-2 group-hover:underline">
            {card.title}
          </p>
          <p className="shrink-0 text-sm font-bold whitespace-nowrap">
            {priceLabel}
            {isRent && <span className="text-muted-foreground text-[10px] font-medium">/mo</span>}
          </p>
        </div>

        <p className="text-muted-foreground flex items-center gap-1 truncate text-xs">
          <MapPinIcon className="size-3 shrink-0" />
          {card.neighborhood ?? card.city}
        </p>

        <OfferBadge offers={card.offers} size="sm" className="w-fit" />

        <div className="text-muted-foreground flex items-center gap-2.5 overflow-hidden text-xs whitespace-nowrap">
          <span className="flex shrink-0 items-center gap-1">
            <BedDoubleIcon className="size-3.5" />
            {card.bedrooms}
          </span>
          <span className="flex shrink-0 items-center gap-1">
            <ShowerHeadIcon className="size-3.5" />
            {card.bathrooms}
          </span>
          {card.sqft && (
            <span className="flex shrink-0 items-center gap-1">
              <SquareIcon className="size-3.5" />
              {card.sqft} sqft
            </span>
          )}
          {visibleAmenities.map((amenity) => (
            <span
              key={amenity}
              className="bg-muted shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium"
            >
              {formatAmenity(amenity)}
            </span>
          ))}
          {hiddenAmenityCount > 0 && (
            <span className="bg-muted shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium">
              +{hiddenAmenityCount}
            </span>
          )}
        </div>
      </div>
    </MotionLink>
  );
}
