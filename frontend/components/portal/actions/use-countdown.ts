'use client';

import { useEffect, useState } from 'react';

export interface Countdown {
  /** Whole seconds left (0 once expired). */
  seconds: number;
  /** "2:41". */
  label: string;
  expired: boolean;
}

/** A once-a-second countdown to an ISO datetime (an OTP's `expires_at`). */
export function useCountdown(expiresAt: string): Countdown {
  const [now, setNow] = useState(() => Date.now());
  const end = Date.parse(expiresAt);

  useEffect(() => {
    if (Date.now() >= end) return;
    const id = window.setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= end) window.clearInterval(id);
    }, 1000);
    return () => window.clearInterval(id);
  }, [end]);

  const seconds = Math.max(0, Math.ceil((end - now) / 1000));
  const label = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  return { seconds, label, expired: seconds === 0 };
}
