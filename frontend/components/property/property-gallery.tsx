'use client';

import { useCallback, useEffect, useState } from 'react';
import useEmblaCarousel from 'embla-carousel-react';
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import { PropertyPhoto } from '@/components/home/property-photo';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

/** A swipeable photo gallery with previous/next buttons and a thumbnail strip. */
export function PropertyGallery({ photos, alt }: { photos: string[]; alt: string }) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: photos.length > 1 });
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    if (!emblaApi) return;
    const onSelect = () => setSelected(emblaApi.selectedScrollSnap());
    onSelect();
    emblaApi.on('select', onSelect);
    emblaApi.on('reInit', onSelect);
    return () => {
      emblaApi.off('select', onSelect);
      emblaApi.off('reInit', onSelect);
    };
  }, [emblaApi]);

  const scrollTo = useCallback((index: number) => emblaApi?.scrollTo(index), [emblaApi]);
  const many = photos.length > 1;

  return (
    <div
      role="region"
      aria-roledescription="carousel"
      aria-label="Photos"
      className="flex flex-col gap-3"
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') emblaApi?.scrollPrev();
        if (event.key === 'ArrowRight') emblaApi?.scrollNext();
      }}
    >
      <div className="relative">
        <div ref={emblaRef} className="overflow-hidden rounded-xl">
          <div className="flex touch-pan-y">
            {photos.map((src, i) => (
              <div
                key={`${src}-${i}`}
                role="group"
                aria-roledescription="slide"
                aria-label={`${i + 1} of ${photos.length}`}
                className="relative aspect-[4/3] min-w-0 shrink-0 grow-0 basis-full sm:aspect-[16/10]"
              >
                <PropertyPhoto
                  src={src}
                  alt={i === 0 ? alt : `${alt}, photo ${i + 1}`}
                  sizes="(min-width: 1152px) 720px, (min-width: 1024px) 62vw, 100vw"
                  priority={i === 0}
                />
              </div>
            ))}
          </div>
        </div>
        {many && (
          <>
            <Button
              type="button"
              variant="secondary"
              size="icon"
              aria-label="Previous photo"
              onClick={() => emblaApi?.scrollPrev()}
              className="bg-background/85 absolute top-1/2 left-3 -translate-y-1/2 rounded-full shadow-sm backdrop-blur-sm"
            >
              <ChevronLeftIcon aria-hidden="true" />
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="icon"
              aria-label="Next photo"
              onClick={() => emblaApi?.scrollNext()}
              className="bg-background/85 absolute top-1/2 right-3 -translate-y-1/2 rounded-full shadow-sm backdrop-blur-sm"
            >
              <ChevronRightIcon aria-hidden="true" />
            </Button>
            <p
              aria-live="polite"
              className="bg-background/85 absolute right-3 bottom-3 rounded-sm px-2 py-1 text-xs font-medium tabular-nums backdrop-blur-sm"
            >
              {selected + 1} / {photos.length}
            </p>
          </>
        )}
      </div>
      {many && (
        <ul className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          {photos.map((src, i) => (
            <li key={`${src}-${i}`} className="shrink-0">
              <button
                type="button"
                onClick={() => scrollTo(i)}
                aria-label={`Show photo ${i + 1}`}
                aria-current={i === selected}
                className={cn(
                  'focus-visible:ring-ring/50 relative block h-16 w-24 overflow-hidden rounded-md border-2 outline-none focus-visible:ring-[3px]',
                  i === selected
                    ? 'border-primary'
                    : 'border-transparent opacity-70 hover:opacity-100'
                )}
              >
                <PropertyPhoto src={src} alt="" sizes="96px" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
