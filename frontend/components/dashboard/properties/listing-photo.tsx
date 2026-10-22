import { cn } from '@/lib/shadcn/utils';

export const PLACEHOLDER_PHOTO = '/listings/placeholder.jpg';

/**
 * A listing photo from any host an admin pastes, so a plain <img> (next/image needs every host
 * allow-listed). A missing or broken URL shows the placeholder instead.
 */
export function ListingPhoto({
  src,
  alt,
  className,
  loading = 'lazy',
}: {
  src: string | null | undefined;
  alt: string;
  className?: string;
  loading?: 'lazy' | 'eager';
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src || PLACEHOLDER_PHOTO}
      alt={alt}
      loading={loading}
      decoding="async"
      referrerPolicy="no-referrer"
      onError={(event) => {
        const img = event.currentTarget;
        // Guard against a loop if the placeholder itself fails.
        if (!img.src.endsWith(PLACEHOLDER_PHOTO)) img.src = PLACEHOLDER_PHOTO;
      }}
      className={cn('bg-muted object-cover', className)}
    />
  );
}
