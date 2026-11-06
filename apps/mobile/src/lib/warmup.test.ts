import assert from 'node:assert/strict';
import { test } from 'node:test';

import { warmupSteps } from './warmup.ts';

test('rounds and ramp sets become steps', () => {
  assert.deepEqual(
    warmupSteps(
      '3 rounds: 10 empty-bar RDLs, 5 kip swings, 250 m easy row. Then 2–3 ramp sets on the main lift (bar → 50% → 70%).',
    ),
    {
      detail: '10 empty-bar RDLs, 5 kip swings, 250 m easy row',
      steps: ['Round 1', 'Round 2', 'Round 3', 'Ramp sets'],
    },
  );
});

test('a car-in warm-up has no ramp sets', () => {
  assert.deepEqual(warmupSteps('3 rounds: 10 band pull-aparts, 10 scap push-ups.'), {
    detail: '10 band pull-aparts, 10 scap push-ups',
    steps: ['Round 1', 'Round 2', 'Round 3'],
  });
});

test('free text is one step', () => {
  assert.deepEqual(warmupSteps('Easy 5 min row'), { detail: 'Easy 5 min row', steps: ['Done'] });
});
