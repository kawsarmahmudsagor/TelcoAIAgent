import type { Metadata } from 'next';
import { headers } from 'next/headers';
import Link from 'next/link';
import { ThemeToggle } from '@/components/app/theme-toggle';
import { Toaster } from '@/components/ui/sonner';
import { getAppConfig, getStyles } from '@/lib/utils';

export async function generateMetadata(): Promise<Metadata> {
  const appConfig = await getAppConfig(await headers());
  // `absolute` so the root layout's "· Horizon Realty" template isn't appended.
  return { title: { absolute: appConfig.pageTitle }, description: appConfig.pageDescription };
}

/** Chrome for the standalone voice/chat page at `/chat`: the corner logo, the hover theme toggle,
 * the configurable accent and the page's own Toaster. `data-surface="widget"` switches
 * styles/globals.css to the widget's original neutral tokens. */
export default async function WidgetLayout({ children }: { children: React.ReactNode }) {
  const appConfig = await getAppConfig(await headers());
  const styles = getStyles(appConfig);
  const { companyName, logo, logoDark } = appConfig;

  return (
    <div data-surface="widget" className="contents">
      {styles && <style>{styles}</style>}
      <header className="pointer-events-none fixed top-0 left-0 z-50 hidden w-full flex-row justify-between p-6 md:flex">
        <Link
          href="/home"
          className="pointer-events-auto scale-100 transition-transform duration-300 hover:scale-110"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={logo}
            alt={`${companyName} Logo`}
            data-logo="light"
            className="block size-6 dark:hidden"
          />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={logoDark ?? logo}
            alt={`${companyName} Logo`}
            data-logo="dark"
            className="hidden size-6 dark:block"
          />
        </Link>
      </header>

      {children}
      {/* Hidden during a call (styles/globals.css): it would sit over End call. */}
      <div
        data-theme-toggle-zone
        className="group fixed bottom-0 left-1/2 z-50 mb-2 -translate-x-1/2"
      >
        <ThemeToggle className="translate-y-20 transition-transform delay-150 duration-300 group-hover:translate-y-0" />
      </div>
      <Toaster position="top-center" />
    </div>
  );
}
