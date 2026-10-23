import { Suspense } from 'react';
import type { Metadata } from 'next';
import { MonitorView } from '@/components/dashboard/monitor/monitor-view';

export const metadata: Metadata = { title: 'AI monitor' };

export default function AiMonitorPage() {
  // The 24 h / 7 d window lives in ?window=, which needs a Suspense boundary.
  return (
    <Suspense>
      <MonitorView />
    </Suspense>
  );
}
