// The customer site's sign-in state lives with its assistant (one check, refreshed on every
// page change), so the header, hero and assistant always agree.
export { type SignedIn, useSignedIn } from '@/components/customer/customer-assistant';
