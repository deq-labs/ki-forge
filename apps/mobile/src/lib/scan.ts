/** Scan screen display helpers. The frame ratio itself always comes from the server. */

export const GAUGE_MIN = 1.2;
export const GAUGE_MAX = 1.8;

/** Where a ratio sits on the 1.20–1.80 gauge, as a 0–100 percentage (clamped to the ends). */
export function gaugePercent(ratio: number): number {
  const clamped = Math.min(GAUGE_MAX, Math.max(GAUGE_MIN, ratio));
  return ((clamped - GAUGE_MIN) / (GAUGE_MAX - GAUGE_MIN)) * 100;
}

/** "0.26 to go. Adding 1" to your shoulders or losing 1" from your waist moves you about 0.03." */
export function scanAdvice(ratio: number | null, target: number, waist: number | null): string {
  if (ratio == null) return 'Log your shoulders and waist to see your frame ratio against your path target.';
  const gap = Math.round((target - ratio) * 100) / 100;
  if (gap <= 0) return `Target reached: ${ratio.toFixed(2)} against ${target.toFixed(2)}. Hold it through Reveal.`;
  // One inch of shoulder changes shoulders/waist by about 1/waist (a waist inch moves it by a similar amount).
  const step =
    waist && waist > 1
      ? ` Adding 1" to your shoulders or losing 1" from your waist moves you about ${(1 / waist).toFixed(2)}.`
      : '';
  return `${gap.toFixed(2)} to go.${step}`;
}
