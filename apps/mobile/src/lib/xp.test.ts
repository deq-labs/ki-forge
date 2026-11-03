// Golden values from docs/03-program-rules.md, the same ones services/api/tests/rules/test_xp.py checks.
// Run with `pnpm --filter @kiforge/mobile test` (Node's built-in test runner; Node 26 runs TypeScript).
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { levelFor, levelProgress, maxSessionXp, rankFor, SET_XP, xpForLevel } from './xp.ts';

const RANKS = [
  { from_level: 1, name: 'Rookie' },
  { from_level: 5, name: 'Fighter' },
  { from_level: 10, name: 'Warrior' },
  { from_level: 15, name: 'Elite' },
  { from_level: 20, name: 'Ascended' },
  { from_level: 25, name: 'Ascended II' },
  { from_level: 30, name: 'Mythic' },
];

describe('levels (golden)', () => {
  for (const [xp, level] of [
    [0, 1],
    [399, 1],
    [400, 2],
    [4_420, 7],
    [55_499, 30],
    [55_500, 31],
  ] as const) {
    it(`${xp} XP is level ${level}`, () => assert.equal(levelFor(xp), level));
  }

  it('7,200 XP to reach level 10', () => assert.equal(xpForLevel(10), 7_200));

  it('is exact at every boundary', () => {
    for (let level = 1; level < 500; level++) {
      const b = xpForLevel(level);
      assert.equal(levelFor(b), level);
      if (b > 0) assert.equal(levelFor(b - 1), level - 1);
    }
  });

  it('rejects bad input', () => {
    assert.throws(() => levelFor(-1), RangeError);
    assert.throws(() => xpForLevel(0), RangeError);
  });
});

describe('progress and ranks (golden)', () => {
  it('Upper A + Trial 0 = 740 XP: level 2, Rookie, 160 to level 3', () => {
    const p = levelProgress(740);
    assert.deepEqual([p.level, p.xpIntoLevel, p.xpToNext], [2, 340, 160]);
    assert.equal(rankFor(p.level, RANKS), 'Rookie');
  });

  it('4,420 XP: 480 to level 8 (the Base mockup)', () => {
    assert.equal(levelProgress(4_420).xpToNext, 480);
  });

  it('ranks at 9 / 10 / 30', () => {
    assert.deepEqual([9, 10, 30].map((l) => rankFor(l, RANKS)), ['Fighter', 'Warrior', 'Mythic']);
  });

  it('a logged set is 5 XP; Upper A logs 23 sets = 115', () => assert.equal(23 * SET_XP, 115));
});

describe('session XP ceiling (golden)', () => {
  it('Upper A: 115 + 125 = 240', () => assert.equal(maxSessionXp(23, 'lift'), 240));
  it('Engine: 5 + 50 = 55, never the +25', () => assert.equal(maxSessionXp(1, 'conditioning'), 55));
});
