import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  isDoneStyle,
  nextOpenRow,
  prescriptionLine,
  progress,
  restSeconds,
  rowsFor,
  setsForRow,
  type Prescription,
} from './train.ts';

const p = (over: Partial<Prescription>): Prescription => ({
  exercise: 'standing-barbell-overhead-press',
  name: 'Standing barbell overhead press',
  swap: 'dumbbell-standing-press',
  is_swap: false,
  sets: 3,
  rep_min: 8,
  rep_max: 10,
  rest_seconds: 150,
  superset_group: null,
  is_main_lift: true,
  is_path_technique: false,
  note: null,
  prefill_weight_lb: 100,
  ...over,
});
const names: Record<string, string> = { 'dumbbell-standing-press': 'Dumbbell standing press' };
const set = (exercise_slug: string, reps = 10, set_no = 1) => ({ exercise_slug, reps, weight_lb: 50, set_no });

describe('garage rows', () => {
  it('keeps the server build when the setting matches', () => {
    const [r] = rowsFor([p({})], false, false, (s) => names[s]);
    assert.equal(r.exercise, 'standing-barbell-overhead-press');
  });

  it('flips to the swap offline when garage is toggled', () => {
    const [r, plain] = rowsFor([p({}), p({ exercise: 'incline-dumbbell-press', swap: null })], false, true, (s) => names[s]);
    assert.deepEqual([r.exercise, r.name, r.is_swap, r.swap, r.prefill_weight_lb], [
      'dumbbell-standing-press',
      'Dumbbell standing press',
      true,
      'standing-barbell-overhead-press',
      null,
    ]);
    assert.equal(plain.exercise, 'incline-dumbbell-press'); // no swap: unchanged
  });

  it('a swapped row also counts sets done as written (matches the server)', () => {
    const [r] = rowsFor([p({})], false, true, (s) => names[s]);
    assert.equal(setsForRow(r, [set('standing-barbell-overhead-press'), set('dumbbell-standing-press')]).length, 2);
    const [gym] = rowsFor([p({})], false, false, (s) => names[s]);
    assert.equal(setsForRow(gym, [set('dumbbell-standing-press')]).length, 0);
  });
});

describe('progress', () => {
  it('caps each row at its prescribed sets (extra sets earn nothing)', () => {
    const rows = rowsFor([p({ sets: 2 }), p({ exercise: 'dips', swap: null, sets: 3 })], false, false, () => undefined);
    const sets = [1, 2, 3, 4].map((n) => set('standing-barbell-overhead-press', 10, n)).concat([set('dips')]);
    assert.deepEqual(progress(rows, sets), { done: 3, needed: 5, rowsDone: [true, false] });
  });

  it('opens the next unfinished row, wrapping around', () => {
    assert.equal(nextOpenRow([true, false, true, false], 1), 3);
    assert.equal(nextOpenRow([false, true, true], 2), 0);
    assert.equal(nextOpenRow([true, true], 0), null);
  });
});

describe('labels and rest', () => {
  it('formats prescriptions', () => {
    assert.equal(prescriptionLine(p({ sets: 4, rep_min: 6, rep_max: 8 })), '4 × 6–8');
    assert.equal(prescriptionLine(p({ rep_min: 12, rep_max: 12, superset_group: 'A' })), '3 × 12 · superset A');
    assert.equal(prescriptionLine(p({ sets: 1, rep_min: 1, rep_max: 1 })), '1 × done');
  });

  it('done-style rows are reps 1 of 1', () => {
    assert.ok(isDoneStyle({ rep_min: 1, rep_max: 1 }));
    assert.ok(!isDoneStyle({ rep_min: 1, rep_max: 5 }));
  });

  it('rests the prescription time, 120 s after the last set, 90 s by default', () => {
    assert.equal(restSeconds({ rest_seconds: 150, sets: 3 }, 1), 150);
    assert.equal(restSeconds({ rest_seconds: 150, sets: 3 }, 3), 120);
    assert.equal(restSeconds({ rest_seconds: null, sets: 3 }, 1), 90);
    assert.equal(restSeconds({ rest_seconds: 0, sets: 3 }, 1), 90);
  });
});

describe('technique steps', async () => {
  const { defaultStep, nextStep } = await import('./train.ts');
  const steps = [
    { exercise: 'box-pistol-squat', name: 'Box pistol', prefill_weight_lb: null },
    { exercise: 'assisted-pistol-squat', name: 'Assisted pistol', prefill_weight_lb: null },
    { exercise: 'pistol-squat-progression', name: 'Full pistol', prefill_weight_lb: null },
  ];
  const tech = p({ exercise: 'pistol-squat-progression', swap: null, is_path_technique: true, steps, current_step: 'assisted-pistol-squat' });

  it('counts sets on any step for the technique row', () => {
    const [row] = rowsFor([tech], false, false, () => undefined);
    assert.equal(setsForRow(row, [set('box-pistol-squat'), set('assisted-pistol-squat'), set('dips')]).length, 2);
  });

  it('defaults to the current step, else the first, and knows the next one', () => {
    assert.equal(defaultStep(tech), 'assisted-pistol-squat');
    assert.equal(defaultStep({ ...tech, current_step: null }), 'box-pistol-squat');
    assert.equal(defaultStep({ steps: [], current_step: null }), null);
    assert.equal(nextStep(tech, 'assisted-pistol-squat')?.name, 'Full pistol');
    assert.equal(nextStep(tech, 'pistol-squat-progression'), null);
  });
});
