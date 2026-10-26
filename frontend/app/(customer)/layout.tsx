import { CustomerAssistant } from '@/components/customer/customer-assistant';

/** The customer site (home, log in, portal) shares one assistant session across its pages. */
export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  return <CustomerAssistant>{children}</CustomerAssistant>;
}
