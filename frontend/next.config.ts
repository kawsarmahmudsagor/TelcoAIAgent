import { networkInterfaces } from 'node:os';
import type { NextConfig } from 'next';

function localIPv4Addresses(): string[] {
  return Object.values(networkInterfaces())
    .flatMap((addrs) => addrs ?? [])
    .filter((a) => a.family === 'IPv4' && !a.internal)
    .map((a) => a.address);
}

// Where the Next.js server forwards `/backend/*` (see lib/api-client.ts). The
// browser only ever talks to this app's own origin, so a single Cloudflare
// tunnel to port 3001 serves both the UI and the API.
const FASTAPI_INTERNAL_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8011';

const nextConfig: NextConfig = {
  // Enables the minimal standalone server output used by frontend/Dockerfile.
  output: 'standalone',
  // Dev server is reachable over the LAN at these IPs and through Cloudflare
  // quick tunnels -- without this, requests to /_next/* from those origins log
  // a cross-origin warning and will be blocked in a future Next.js major version.
  // Every IPv4 on this machine is allowed, so a DHCP change needs no edit here.
  allowedDevOrigins: [...localIPv4Addresses(), '*.trycloudflare.com'],
  // Hide the "N" dev-tools badge Next.js floats over the page in dev mode.
  devIndicators: false,
  // Seeded listing photos. Admin-entered image URLs can be on any host, so
  // those render with a plain <img> instead of next/image.
  images: {
    remotePatterns: [{ protocol: 'https', hostname: 'images.unsplash.com' }],
  },
  async redirects() {
    return [
      // The public site lives at /home; the agent is the chat bubble on every (site) page.
      { source: '/', destination: '/home', permanent: false },
      // Voice settings moved into the Chatbot page's "Model & voice" tab.
      {
        source: '/dashboard/voice',
        destination: '/dashboard/chatbot?tab=model',
        permanent: true,
      },
    ];
  },
  async rewrites() {
    return [{ source: '/backend/:path*', destination: `${FASTAPI_INTERNAL_URL}/:path*` }];
  },
};

export default nextConfig;
