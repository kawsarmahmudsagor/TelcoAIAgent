'use client';

import { useCallback, useEffect, useRef } from 'react';

const RING_ON_MS = 2000;
const RING_CYCLE_MS = 6000;
const RING_FREQUENCIES_HZ = [440, 480];
const RING_GAIN = 0.12;

/**
 * Plays a classic phone ring (440 + 480 Hz dual tone, 2s on / 4s off) while
 * `active` is true, synthesized with the Web Audio API so there's no audio
 * asset to ship. If the browser blocks autoplay (no prior user interaction on
 * the page) it just stays silent. Returns `stop()` to silence it immediately,
 * e.g. right as the call is answered/declined.
 */
export function useRingtone(active: boolean) {
  const contextRef = useRef<AudioContext | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    contextRef.current?.close().catch(() => {});
    contextRef.current = null;
  }, []);

  useEffect(() => {
    if (!active) return;

    let context: AudioContext;
    try {
      context = new AudioContext();
    } catch {
      return; // no Web Audio support
    }
    contextRef.current = context;

    const ringOnce = () => {
      if (context.state !== 'running') return;
      const start = context.currentTime;
      const end = start + RING_ON_MS / 1000;
      const gain = context.createGain();
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(RING_GAIN, start + 0.02);
      gain.gain.setValueAtTime(RING_GAIN, end - 0.02);
      gain.gain.linearRampToValueAtTime(0, end);
      gain.connect(context.destination);
      for (const frequency of RING_FREQUENCIES_HZ) {
        const oscillator = context.createOscillator();
        oscillator.frequency.value = frequency;
        oscillator.connect(gain);
        oscillator.start(start);
        oscillator.stop(end);
      }
    };

    // A fresh AudioContext may start suspended; ring as soon as it's allowed to run.
    context
      .resume()
      .then(ringOnce)
      .catch(() => {});
    intervalRef.current = setInterval(ringOnce, RING_CYCLE_MS);
    return stop;
  }, [active, stop]);

  return stop;
}
