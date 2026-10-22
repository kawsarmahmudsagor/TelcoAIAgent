import { cn } from '@/lib/shadcn/utils';

const HORIZON = 168;

// [x, width, height] of each tower, left to right. Hand-placed so the skyline reads as a dense
// city edge. The far towers stand behind the sun; the two near ones cut across it.
const FAR_TOWERS: [number, number, number][] = [
  [0, 34, 58],
  [30, 26, 84],
  [52, 40, 46],
  [88, 22, 104],
  [108, 36, 72],
  [140, 28, 124],
  [164, 44, 64],
  [204, 24, 92],
  [224, 38, 56],
  [258, 30, 112],
  [476, 36, 60],
  [508, 24, 116],
  [528, 42, 74],
  [566, 34, 94],
];

const NEAR_TOWERS: [number, number, number][] = [
  [342, 26, 138],
  [396, 22, 150],
];

// A few lit windows, as [x, y] — sparse on purpose.
const WINDOWS: [number, number][] = [
  [146, 60],
  [154, 82],
  [264, 74],
  [348, 52],
  [356, 92],
  [402, 40],
  [402, 66],
  [514, 80],
  [94, 92],
];

/**
 * Dhaka at dusk: towers standing on the horizon, the brass sun setting behind them and its
 * reflection breaking up on the river below. Decorative only.
 */
export function Skyline({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 600 230"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
      className={cn('block w-full', className)}
    >
      <defs>
        <clipPath id="skyline-above-horizon">
          <rect x="0" y="0" width="600" height={HORIZON} />
        </clipPath>
      </defs>

      {FAR_TOWERS.map(([x, w, h]) => (
        <rect
          key={x}
          x={x}
          y={HORIZON - h}
          width={w}
          height={h}
          className="fill-[color-mix(in_oklab,var(--sidebar)_70%,black)]"
        />
      ))}
      <circle
        cx="372"
        cy={HORIZON}
        r="92"
        className="fill-brass"
        opacity="0.9"
        clipPath="url(#skyline-above-horizon)"
      />

      {NEAR_TOWERS.map(([x, w, h]) => (
        <rect
          key={x}
          x={x}
          y={HORIZON - h}
          width={w}
          height={h}
          className="fill-[color-mix(in_oklab,var(--sidebar)_35%,black)]"
        />
      ))}
      {WINDOWS.map(([x, y]) => (
        <rect
          key={`${x}-${y}`}
          x={x}
          y={y}
          width="4"
          height="6"
          className="fill-brass"
          opacity="0.7"
        />
      ))}

      <rect x="0" y={HORIZON} width="600" height="2" className="fill-brass" opacity="0.85" />

      {/* The sun's reflection on the river: shorter and fainter as it nears the viewer. */}
      {[
        [300, 144, 178, 0.55],
        [318, 108, 188, 0.4],
        [336, 72, 198, 0.28],
        [350, 44, 208, 0.18],
        [360, 24, 218, 0.1],
      ].map(([x, w, y, o]) => (
        <rect
          key={y}
          x={x}
          y={y}
          width={w}
          height="2.5"
          rx="1.25"
          className="fill-brass"
          opacity={o}
        />
      ))}
    </svg>
  );
}
