import Image from 'next/image';
import { cn } from '@/lib/shadcn/utils';

const PLACEHOLDER = '/listings/placeholder.jpg';
const OPTIMISED_HOSTS = new Set(['images.unsplash.com']);

function isOptimisedHost(src: string): boolean {
  try {
    return OPTIMISED_HOSTS.has(new URL(src).hostname);
  } catch {
    return false;
  }
}

/**
 * A photo that fills its (relatively positioned, sized) parent. Seeded Unsplash photos go
 * through next/image; anything else an admin pasted renders as a plain <img>, because
 * next/image only accepts allow-listed hosts.
 */
export function PropertyPhoto({
  src,
  alt,
  sizes,
  priority = false,
  className,
}: {
  src: string | null | undefined;
  alt: string;
  sizes: string;
  priority?: boolean;
  className?: string;
}) {
  const classes = cn('bg-muted absolute inset-0 size-full object-cover', className);
  if (src && isOptimisedHost(src)) {
    return <Image src={src} alt={alt} fill sizes={sizes} priority={priority} className={classes} />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src || PLACEHOLDER}
      alt={alt}
      loading={priority ? 'eager' : 'lazy'}
      decoding="async"
      referrerPolicy="no-referrer"
      className={classes}
    />
  );
}
