/**
 * XP display helper (CLAUDE.md rule 1). The server is authoritative for every XP number; the app only
 * uses this to show optimistic values (+5 XP on a logged set) until the sync response replaces them.
 * Mirrors services/api/app/rules/xp.py; xp.test.ts checks the same golden values.
 */

/** Optimistic XP for one logged set (counts only up to the prescribed sets). */
export const SET_XP = 5;

/** Total XP needed to be `level` (level 1 needs 0): 50(L-1)² + 350(L-1). */
export function xpForLevel(level: number): number {
  if (!Number.isInteger(level) || level < 1) throw new RangeError(`level must be an integer >= 1, got ${level}`);
  const k = level - 1;
  return 50 * k * k + 350 * k;
}

/** Level for a total XP, exact at every boundary (formula, then corrected by ±1). */
export function levelFor(xp: number): number {
  if (!Number.isFinite(xp) || xp < 0) throw new RangeError(`xp must be >= 0, got ${xp}`);
  let level = Math.floor((-350 + Math.sqrt(350 * 350 + 200 * xp)) / 100) + 1;
  while (level > 1 && xpForLevel(level) > xp) level -= 1;
  while (xpForLevel(level + 1) <= xp) level += 1;
  return level;
}

export type LevelProgress = { level: number; xp: number; xpIntoLevel: number; xpToNext: number; fraction: number };

/** Where a total XP sits within its level (the HUD's ring and bar show this, not total XP). */
export function levelProgress(xp: number): LevelProgress {
  const level = levelFor(xp);
  const floor = xpForLevel(level);
  const next = xpForLevel(level + 1);
  return { level, xp, xpIntoLevel: xp - floor, xpToNext: next - xp, fraction: (xp - floor) / (next - floor) };
}

/** Rank name for a level from the program's ranks (`{from_level, name}`, any order). */
export function rankFor(level: number, ranks: readonly { from_level: number; name: string }[]): string {
  let best: { from_level: number; name: string } | undefined;
  for (const r of ranks) if (r.from_level <= level && (!best || r.from_level > best.from_level)) best = r;
  return best?.name ?? '';
}
