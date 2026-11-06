import assert from 'node:assert/strict';
import { test } from 'node:test';

import { themeColors, themePathColors, themes } from './tokens.ts';

// WCAG relative luminance and contrast ratio (CLAUDE.md rule 8: text ≥ 4.5:1).
function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [16, 8, 0].map((s) => {
    const c = ((n >> s) & 255) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

type C = (typeof themeColors)[keyof typeof themeColors];

// [text, backgrounds, minimum]: the pairings the token usage notes promise.
const PAIRS: [keyof C, (keyof C)[], number][] = [
  ['ink', ['night900', 'night800', 'panel', 'panelRaised'], 4.5],
  ['inkMuted', ['night900', 'panel', 'panelRaised'], 4.5],
  ['inkFaint', ['night900', 'panel'], 4.5],
  ['onKi', ['ki'], 4.5],
  ['volt', ['night900', 'panel'], 4.5],
  ['good', ['panel'], 4.5],
  ['danger', ['panel'], 4.5],
  ['kiHot', ['panel'], 4.5],
  // Background-colored text on filled chips (done ticks, active chips).
  ['night900', ['good', 'volt', 'danger', 'ki', 'kiHot'], 4.5],
];

test('every theme has the same color tokens', () => {
  const names = Object.keys(themeColors.night).sort();
  for (const t of themes) assert.deepEqual(Object.keys(themeColors[t.id]).sort(), names, t.id);
});

for (const t of themes) {
  test(`${t.name}: text colors reach their contrast minimums`, () => {
    const c = themeColors[t.id] as C;
    for (const [fg, bgs, min] of PAIRS)
      for (const bg of bgs) {
        const r = contrast(c[fg], c[bg]);
        assert.ok(r >= min, `${t.id}: ${String(fg)} on ${String(bg)} is ${r.toFixed(2)}, needs ${min}`);
      }
  });

  test(`${t.name}: every path color works for buttons and on panels`, () => {
    const c = themeColors[t.id] as C;
    for (const [slug, pair] of Object.entries(themePathColors[t.id])) {
      const onKi = contrast(c.onKi, pair.ki);
      assert.ok(onKi >= 4.5, `${t.id}/${slug}: button text ${onKi.toFixed(2)}`);
      const onPanel = contrast(pair.ki, c.panel);
      assert.ok(onPanel >= 3, `${t.id}/${slug}: on panel ${onPanel.toFixed(2)}`);
    }
  });
}
