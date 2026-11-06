/** 1RM entry and display helpers (Iron Tempo). The server stores lb (CLAUDE.md rule 4). */

export const KG_PER_LB = 0.45359237;

/** lb → display units, rounded to 0.5 kg or 1 lb. */
export function fromLb(lb: number, units: 'imperial' | 'metric'): number {
  return units === 'metric' ? Math.round(lb * KG_PER_LB * 2) / 2 : Math.round(lb);
}

/** A display value for a text input ("102.5", "305"). */
export function liftInput(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/**
 * A typed 1RM → lb. Empty = not entered (null); anything that is not a weight between 0 and 2000 lb is
 * 'invalid'. Commas work as decimal points.
 */
export function parseLift(text: string, units: 'imperial' | 'metric'): number | null | 'invalid' {
  const t = text.trim().replace(',', '.');
  if (t === '') return null;
  const v = Number(t);
  if (!Number.isFinite(v) || v <= 0) return 'invalid';
  const lb = units === 'metric' ? Math.round((v / KG_PER_LB) * 10) / 10 : v;
  return lb < 2000 ? lb : 'invalid';
}

/** A load for display: "245 lb", or "111 kg" for metric. */
export function formatLoad(lb: number, units: 'imperial' | 'metric'): string {
  return units === 'metric' ? `${liftInput(fromLb(lb, units))} kg` : `${liftInput(fromLb(lb, units))} lb`;
}
