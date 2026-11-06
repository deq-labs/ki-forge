import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  afterSet,
  blockSeconds,
  intervalState,
  levelOf,
  nextRound,
  prescriptionLine,
  progress,
  roundsLogged,
  setsForRow,
  targetLine,
  type BlockInfo,
  type Level,
  type Row,
} from './train.ts';

const lv = (over: Partial<Level>): Level => ({
  amount: 3,
  unit: 'reps',
  percent: null,
  weight_lb: null,
  exercise: 'x',
  name: 'X',
  ...over,
});

// Iron Tempo Monday: 21:00 alt EMOM, 7 rounds.
const emom: BlockInfo = {
  kind: 'emom',
  name: '21:00 Alt EMOM',
  rounds: 7,
  interval_seconds: 60,
  cap_seconds: null,
  rest_seconds: null,
  minutes: 21,
  movements: [
    {
      exercise: 'conventional-deadlift',
      name: 'Deadlift',
      note: null,
      levels: [75, 80, 85].map((p, i) =>
        lv({ percent: p, weight_lb: [230, 240, 260][i], exercise: 'conventional-deadlift' }),
      ),
    },
    {
      exercise: 'chest-to-bar-pull-up',
      name: 'C2B',
      note: null,
      levels: [lv({ amount: 8, exercise: 'pull-up' }), lv({ amount: 10, exercise: 'chest-to-bar-pull-up' })],
    },
    {
      exercise: 'calorie-row',
      name: 'Row',
      note: null,
      levels: [lv({ amount: 12, unit: 'cal', exercise: 'calorie-row' })],
    },
  ],
};

const row = (over: Partial<Row> = {}): Row => ({
  exercise: 'conventional-deadlift',
  name: '21:00 Alt EMOM',
  swap: null,
  is_swap: false,
  sets: 7,
  rep_min: 1,
  rep_max: 1,
  rest_seconds: null,
  superset_group: null,
  is_main_lift: false,
  is_path_technique: false,
  note: null,
  prefill_weight_lb: null,
  key: 'p0',
  role: 'main',
  block: emom,
  index: 0,
  ...over,
});

const s = (exercise_slug: string, set_no: number, slot: string | null = 'p0') => ({
  exercise_slug,
  set_no,
  reps: 3,
  weight_lb: 0,
  slot,
});
const round = (n: number, c2b = 'chest-to-bar-pull-up') => [
  s('conventional-deadlift', n),
  s(c2b, n),
  s('calorie-row', n),
];

describe('block rounds', () => {
  it('counts a round only when every movement is logged', () => {
    const sets = [...round(1), s('conventional-deadlift', 2), s('chest-to-bar-pull-up', 2)];
    assert.deepEqual(roundsLogged(row(), sets), [1]);
    assert.equal(nextRound(row(), sets), 2);
  });

  it('accepts a level swap (pull-ups at L1)', () => {
    assert.deepEqual(roundsLogged(row(), round(1, 'pull-up')), [1]);
  });

  it('only counts sets with the row key', () => {
    const finisher = [
      s('conventional-deadlift', 1, 'p1'),
      s('chest-to-bar-pull-up', 1, 'p1'),
      s('calorie-row', 1, 'p1'),
    ];
    assert.deepEqual(roundsLogged(row(), finisher), []);
    // and a plain row ignores block sets of the same exercise
    const plain = row({ key: 'p2', block: null, sets: 3 });
    assert.equal(setsForRow(plain, [...round(1), s('conventional-deadlift', 1, null)]).length, 1);
  });

  it('feeds progress with rounds', () => {
    const sets = [1, 2, 3].flatMap((n) => round(n));
    const p = progress([row()], sets);
    assert.deepEqual([p.done, p.needed, p.rowsDone[0]], [3, 7, false]);
  });

  it('runs on its own clock: no rest timer, stays open until done', () => {
    const prefs = { restEnabled: true, restAdjust: 0, supersetTransition: 0, perExercise: {} };
    assert.deepEqual(afterSet([row()], 0, [3], prefs), { rest: null, open: 0 });
    const circuit = row({ block: { ...emom, kind: 'circuit', rest_seconds: 30 } });
    assert.deepEqual(afterSet([circuit], 0, [1], prefs), { rest: 30, open: 0 });
  });
});

describe('targets', () => {
  const load = (lb: number) => `${lb} lb`;
  it('formats each kind', () => {
    assert.equal(targetLine(levelOf(emom.movements[0], 1), load), '3 @ 80% · 240 lb');
    assert.equal(targetLine(lv({ percent: 80 }), load), '3 @ 80%'); // no 1RM yet
    assert.equal(targetLine(lv({ amount: 15, unit: 'cal' }), load), '15 cal');
    assert.equal(targetLine(lv({ amount: 20, unit: 'steps' }), load), '20 steps');
    assert.equal(targetLine(lv({ amount: 30, unit: 'seconds' }), load), '30 s');
    assert.equal(targetLine(lv({ amount: 10, weight_lb: 50 }), load), '10 × 50 lb');
    assert.equal(targetLine(lv({ amount: null, unit: 'cal' }), load), 'Max cal');
  });
  it('clamps the level to the levels a movement has', () => {
    assert.equal(levelOf(emom.movements[2], 2).amount, 12);
  });
  it('describes the block', () => {
    assert.equal(prescriptionLine(row()), '7 rounds · 21:00');
    assert.equal(
      prescriptionLine(row({ block: { ...emom, kind: 'for_time', rounds: 5, cap_seconds: 900, minutes: null } })),
      '5 rounds · cap 15:00',
    );
  });
});

describe('interval timer', () => {
  it('rotates EMOM movements each minute', () => {
    assert.deepEqual(intervalState(emom, 0), { elapsed: 0, round: 1, movement: 0, secondsLeft: 60, finished: false });
    assert.deepEqual(intervalState(emom, 61.5), {
      elapsed: 61,
      round: 1,
      movement: 1,
      secondsLeft: 59,
      finished: false,
    });
    assert.deepEqual(intervalState(emom, 180), {
      elapsed: 180,
      round: 2,
      movement: 0,
      secondsLeft: 60,
      finished: false,
    });
    assert.equal(intervalState(emom, 1259).round, 7);
    assert.equal(intervalState(emom, 1260).finished, true);
    assert.equal(blockSeconds(emom), 21 * 60);
  });
  it('does every movement each interval for "every 2:30"', () => {
    const every = { ...emom, kind: 'interval', rounds: 6, interval_seconds: 150 };
    assert.deepEqual(intervalState(every, 160), {
      elapsed: 160,
      round: 2,
      movement: null,
      secondsLeft: 140,
      finished: false,
    });
    assert.equal(blockSeconds(every), 900);
  });
  it('counts toward the cap for time', () => {
    const ft = { ...emom, kind: 'for_time', rounds: 5, interval_seconds: null, cap_seconds: 900 };
    assert.deepEqual(intervalState(ft, 300), {
      elapsed: 300,
      round: 1,
      movement: null,
      secondsLeft: 600,
      finished: false,
    });
    assert.equal(intervalState(ft, 900).finished, true);
  });
});
