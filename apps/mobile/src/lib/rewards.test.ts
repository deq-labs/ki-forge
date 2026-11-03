import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { breakdown, momentOf, nextRankLine, type Reward } from './rewards.ts';

const RANKS = [
  { from_level: 1, name: 'Rookie' },
  { from_level: 5, name: 'Fighter' },
  { from_level: 10, name: 'Warrior' },
  { from_level: 30, name: 'Mythic' },
];

const reward = (over: Partial<Reward>): Reward => ({ xp_awarded: [], sessions: [], level_up: null, new_badges: [], ...over });

// The final sync of the golden Upper A: last set plus the bonuses; earlier sets were awarded before.
const upperA = reward({
  xp_awarded: [
    { type: 'set_logged', amount: 5, source_id: 'set-23' },
    { type: 'session_cleared', amount: 100, source_id: 'sess' },
    { type: 'all_on_target', amount: 25, source_id: 'sess' },
  ],
  sessions: [{ client_id: 'sess', cleared: true, all_on_target: true, xp: 240 }],
});

describe('rewards', () => {
  it('breaks a cleared quest into the server totals (golden Upper A = 240)', () => {
    const b = breakdown(upperA);
    assert.deepEqual(b.lines, [
      { label: '23 sets logged', xp: 115 },
      { label: 'Session cleared', xp: 100 },
      { label: 'Every set on target', xp: 25 },
    ]);
    assert.equal(b.total, 240);
    assert.equal(momentOf(upperA), 'quest');
  });

  it('adds the full week bonus', () => {
    const r = { ...upperA, xp_awarded: [...upperA.xp_awarded, { type: 'full_week', amount: 150, source_id: 'week:e:1' }] };
    assert.equal(breakdown(r).total, 390);
  });

  it('classifies moments', () => {
    assert.equal(momentOf(reward({ xp_awarded: [{ type: 'set_logged', amount: 5, source_id: 'x' }] })), null);
    assert.equal(momentOf(reward({ new_badges: [{ slug: 'b', name: 'B', description: '', xp_reward: 75 }] })), 'badge');
    assert.equal(momentOf({ ...upperA, level_up: { from: 1, to: 2, rank: 'Rookie' } }), 'level_up');
  });

  it('a completed Trial is a moment with its 500 XP line', () => {
    const r = reward({ xp_awarded: [{ type: 'trial_completed', amount: 500, source_id: 'trial:e:0' }] });
    assert.equal(momentOf(r), 'quest');
    assert.deepEqual(breakdown(r).lines, [{ label: 'Trial complete', xp: 500 }]);
  });

  it('says how far the next rank is', () => {
    assert.equal(nextRankLine(8, RANKS), 'Two levels to Warrior rank.');
    assert.equal(nextRankLine(2, RANKS), 'Three levels to Fighter rank.');
    assert.equal(nextRankLine(12, RANKS), '18 levels to Mythic rank.');
    assert.equal(nextRankLine(31, RANKS), null);
  });
});
