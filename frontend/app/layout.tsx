import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import localFont from 'next/font/local';
import { ThemeProvider } from '@/components/app/theme-provider';
import { cn } from '@/lib/shadcn/utils';
import '@/styles/globals.css';

// The telco face for everything: body, page titles and figures (spec 6.6).
const inter = Inter({
  variable: '--font-inter',
  subsets: ['latin'],
});

const commitMono = localFont({
  display: 'swap',
  variable: '--font-commit-mono',
  src: [
    {
      path: '../fonts/CommitMono-400-Regular.otf',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-700-Regular.otf',
      weight: '700',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-400-Italic.otf',
      weight: '400',
      style: 'italic',
    },
    {
      path: '../fonts/CommitMono-700-Italic.otf',
      weight: '700',
      style: 'italic',
    },
  ],
});

export const metadata: Metadata = {
  title: { default: 'telco', template: '%s · telco' },
  description: 'telco self-care portal and AI assistant (demo)',
};

interface RootLayoutProps {
  children: React.ReactNode;
}

/** Shared by every route: fonts, tokens and the colour scheme. Each surface (the persona picker,
 * the customer portal, the admin dashboard, the login page) brings its own chrome. */
export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(inter.variable, commitMono.variable, 'scroll-smooth font-sans antialiased')}
    >
      <body className="overflow-x-hidden">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
