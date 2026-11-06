/**
 * Pure helpers for the Train screen. This is display logic only: what to show and what is logged.
 * Whether a session is cleared and what it earns is decided by the server on sync (CLAUDE.md rule 1).
 */

export type Prescription = {
  exercise: string;
  name: string;
  swap: string | null; // the other option for the other garage setting
  is_swap: boolean;
  sets: number;
  rep_min: number;
  rep_max: number;
  rest_seconds: number | null;
  superset_group: string | null;
  is_main_lift: boolean;
  is_path_technique: boolean;
  note: string | null;
  prefill_weight_lb: number | null;
  /** Technique progression steps (easiest first), the one you're on, and whether to try the next one. */
  steps?: { exercise: string; name: string; prefill_weight_lb: number | null }[];
  current_step?: string | null;
  ready_to_advance?: boolean;
  /** Row id within the session; a block round's sets carry it as `slot`. */
  key?: string;
  role?: string | null;
  /** Timed multi-movement work (EMOM, interval, for time, circuit); `sets` = rounds. */
  block?: BlockInfo | null;
};

export type Level = {
  amount: number | null; // null = max effort
  unit: string; // reps | cal | steps | seconds
  percent: number | null;
  weight_lb: number | null; // from your 1RM, or the fixed load; null until a 1RM is entered
  exercise: string;
  name: string;
};
export type Movement = { exercise: string; name: string; note: string | null; levels: Level[] };
export type BlockInfo = {
  kind: string; // emom | interval | for_time | circuit
  name: string;
  rounds: number;
  interval_seconds: number | null;
  cap_seconds: number | null;
  rest_seconds: number | null;
  minutes: number | null;
  movements: Movement[];
};

export type Row = Prescription & { index: number };

/**
 * The rows to show for a garage setting. The server built the session for `builtGarage`; each
 * prescription's `swap` is the exercise for the other setting, so flipping garage mode works offline.
 */
export function rowsFor(
  prescriptions: Prescription[],
  builtGarage: boolean,
  garage: boolean,
  nameOf: (slug: string) => string | undefined,
): Row[] {
  return prescriptions.map((p, index) => {
    if (garage === builtGarage || !p.swap) return { ...p, index };
    return {
      ...p,
      index,
      exercise: p.swap,
      name: nameOf(p.swap) ?? p.swap,
      swap: p.exercise,
      is_swap: !p.is_swap,
      prefill_weight_lb: null, // progression is tracked per exercise performed
    };
  });
}

/** Done-style rows (conditioning, carries, holds) are logged as reps = 1 against rep_max = 1. */
export function isDoneStyle(p: Pick<Prescription, 'rep_min' | 'rep_max'>): boolean {
  return p.rep_max === 1 && p.rep_min === 1;
}

export type LoggedLike = {
  exercise_slug: string;
  reps: number | null;
  weight_lb: number;
  set_no: number;
  slot?: string | null;
};

/**
 * Logged sets for a row: its exercise, the one a swapped row replaces, or any of a technique's progression
 * steps (matches the server's scoring).
 */
export function setsForRow<T extends LoggedLike>(
  row: Pick<Row, 'exercise' | 'swap' | 'is_swap' | 'steps' | 'key' | 'block'>,
  sets: T[],
): T[] {
  if (row.block) return sets.filter((s) => s.slot != null && s.slot === row.key); // block rounds carry the row key
  const steps = new Set(row.steps?.map((s) => s.exercise));
  return sets.filter(
    (s) =>
      !s.slot &&
      (s.exercise_slug === row.exercise || (row.is_swap && s.exercise_slug === row.swap) || steps.has(s.exercise_slug)),
  );
}

/** A movement's target at a level (0 = L1); blocks without levels have one. */
export function levelOf(m: Movement, level: number): Level {
  return m.levels[Math.min(level, m.levels.length - 1)];
}

/** Exercises that count for a movement: its own and any level's (e.g. pull-ups at L1 for chest-to-bar). */
export function accepts(m: Movement): Set<string> {
  return new Set([m.exercise, ...m.levels.map((l) => l.exercise)]);
}

/** Rounds (1-based) in which every movement is logged; a complete round counts as one set (matches the server). */
export function roundsLogged<T extends LoggedLike>(row: Pick<Row, 'block' | 'key'>, sets: T[]): number[] {
  const block = row.block;
  if (!block) return [];
  const mine = sets.filter((s) => s.slot === row.key);
  const out: number[] = [];
  for (let n = 1; n <= block.rounds; n++) {
    if (block.movements.every((m) => mine.some((s) => s.set_no === n && accepts(m).has(s.exercise_slug)))) out.push(n);
  }
  return out;
}

/** Sets (or complete rounds) that count for a row. */
export function doneFor<T extends LoggedLike>(row: Row, sets: T[]): number {
  return row.block ? roundsLogged(row, sets).length : setsForRow(row, sets).length;
}

/** The next round to log: the first one not complete, or null when all are. */
export function nextRound<T extends LoggedLike>(row: Pick<Row, 'block' | 'key'>, sets: T[]): number | null {
  if (!row.block) return null;
  const done = new Set(roundsLogged(row, sets));
  for (let n = 1; n <= row.block.rounds; n++) if (!done.has(n)) return n;
  return null;
}

/** "3 @ 80% · 240 lb", "15 cal", "20 steps", "30 s", "10 × 50 lb", "Max cal". */
export function targetLine(l: Level, load: (lb: number) => string): string {
  const unit = l.unit === 'cal' ? ' cal' : l.unit === 'steps' ? ' steps' : l.unit === 'seconds' ? ' s' : '';
  const amount = l.amount == null ? `Max${unit}` : `${l.amount}${unit}`;
  if (l.percent != null) return `${amount} @ ${l.percent}%${l.weight_lb != null ? ` · ${load(l.weight_lb)}` : ''}`;
  if (l.weight_lb != null) return `${amount} × ${load(l.weight_lb)}`;
  return amount;
}

type TimedBlock = Pick<BlockInfo, 'kind' | 'rounds' | 'interval_seconds' | 'cap_seconds' | 'movements'>;

export type IntervalState = {
  elapsed: number; // seconds since start
  round: number; // 1-based, capped at the block's rounds
  movement: number | null; // index of the movement up now (EMOM), else null (all movements each interval)
  secondsLeft: number; // in this interval (EMOM, interval) or until the cap (for time)
  finished: boolean;
};

/** Where an interval timer is after `elapsed` seconds (pure; the clock is the wall clock). */
export function intervalState(block: TimedBlock, elapsed: number): IntervalState {
  const t = Math.max(0, Math.floor(elapsed));
  if (block.kind === 'for_time' || !block.interval_seconds) {
    const cap = block.cap_seconds ?? 0;
    return {
      elapsed: t,
      round: 1,
      movement: null,
      secondsLeft: cap ? Math.max(0, cap - t) : 0,
      finished: cap > 0 && t >= cap,
    };
  }
  const n = block.kind === 'emom' ? Math.max(1, block.movements.length) : 1;
  const slots = block.rounds * n;
  const slot = Math.floor(t / block.interval_seconds);
  const finished = slot >= slots;
  const at = Math.min(slot, slots - 1);
  return {
    elapsed: t,
    round: Math.floor(at / n) + 1,
    movement: block.kind === 'emom' ? at % n : null,
    secondsLeft: finished ? 0 : block.interval_seconds - (t % block.interval_seconds),
    finished,
  };
}

/** Total seconds of a timed block (EMOM and interval), or its cap (for time). */
export function blockSeconds(block: TimedBlock): number {
  if (block.kind === 'for_time' || !block.interval_seconds) return block.cap_seconds ?? 0;
  return block.rounds * block.interval_seconds * (block.kind === 'emom' ? block.movements.length : 1);
}

/** The step to log by default: the one you're on, else the first. */
export function defaultStep(row: Pick<Row, 'steps' | 'current_step'>): string | null {
  if (!row.steps?.length) return null;
  return row.steps.some((s) => s.exercise === row.current_step) ? row.current_step! : row.steps[0].exercise;
}

/** The step after `slug`, or null at the last one. */
export function nextStep(row: Pick<Row, 'steps'>, slug: string | null): { exercise: string; name: string } | null {
  const i = row.steps?.findIndex((s) => s.exercise === slug) ?? -1;
  return i >= 0 && row.steps && i < row.steps.length - 1 ? row.steps[i + 1] : null;
}

export type Progress = { done: number; needed: number; rowsDone: boolean[] };

/** Sets that count toward the session (capped at each row's prescribed sets; extra sets earn nothing). */
export function progress<T extends LoggedLike>(rows: Row[], sets: T[]): Progress {
  const rowsDone = rows.map((r) => doneFor(r, sets) >= r.sets);
  const done = rows.reduce((n, r) => n + Math.min(r.sets, doneFor(r, sets)), 0);
  return { done, needed: rows.reduce((n, r) => n + r.sets, 0), rowsDone };
}

export type RestPrefs = {
  restEnabled: boolean;
  restAdjust: number; // seconds added to every program rest
  supersetTransition: number; // between superset partners; 0 = none
  perExercise: Record<string, number>; // your own rest per exercise slug
};

/** A row's rest between its sets: your override, else the program's (60 s if unset) plus your adjustment. */
export function baseRest(row: Pick<Row, 'exercise' | 'rest_seconds'>, prefs: RestPrefs): number {
  const own = prefs.perExercise[row.exercise];
  if (own != null) return own;
  const program = row.rest_seconds && row.rest_seconds > 0 ? row.rest_seconds : 60;
  return Math.max(15, program + prefs.restAdjust);
}

/**
 * What happens after a set: how long to rest (null = no timer) and which card to open (null = all done).
 * - Superset partners alternate (A1 → A2 → A1 …) with only the transition between them, and the pair's rest
 *   after the last partner of each round.
 * - Within an exercise: its rest. After its last set: the next exercise's rest (setup time for what's next).
 */
export function afterSet(
  rows: Row[],
  index: number,
  setsDone: number[],
  prefs: RestPrefs,
): { rest: number | null; open: number | null } {
  const isDone = (i: number) => setsDone[i] >= rows[i].sets;
  const timer = (seconds: number | null) => (prefs.restEnabled && seconds && seconds > 0 ? seconds : null);
  const row = rows[index];
  const group = row.superset_group
    ? rows.filter((r) => r.superset_group === row.superset_group).map((r) => r.index)
    : [];

  if (row.block) {
    // Timed blocks run on their own clock; a circuit rests between rounds.
    if (!isDone(index))
      return { rest: timer(row.block.kind === 'circuit' ? row.block.rest_seconds : null), open: index };
  } else if (group.length > 1) {
    const pos = group.indexOf(index);
    const pairRest = Math.max(...group.map((i) => baseRest(rows[i], prefs)));
    for (let k = 1; k < group.length; k++) {
      const j = group[(pos + k) % group.length];
      if (!isDone(j)) {
        const sameRound = group.indexOf(j) > pos; // moving on within the round, not wrapping to a new one
        return { rest: timer(sameRound ? prefs.supersetTransition : pairRest), open: j };
      }
    }
    if (!isDone(index)) return { rest: timer(pairRest), open: index }; // partners done; finish this one
  } else if (!isDone(index)) {
    return { rest: timer(baseRest(row, prefs)), open: index };
  }

  const next = nextOpenRow(
    rows.map((_, i) => isDone(i)),
    index,
  );
  return { rest: next === null ? null : timer(baseRest(rows[next], prefs)), open: next };
}

/** "4 × 6–8 · superset A" */
export function prescriptionLine(r: Pick<Row, 'sets' | 'rep_min' | 'rep_max' | 'superset_group' | 'block'>): string {
  if (r.block) {
    const b = r.block;
    const clock =
      b.kind === 'for_time' && b.cap_seconds
        ? ` · cap ${Math.round(b.cap_seconds / 60)}:00`
        : b.minutes
          ? ` · ${b.minutes}:00`
          : '';
    return `${b.rounds} rounds${clock}`;
  }
  const reps = isDoneStyle(r) ? 'done' : r.rep_min === r.rep_max ? `${r.rep_max}` : `${r.rep_min}–${r.rep_max}`;
  return `${r.sets} × ${reps}${r.superset_group ? ` · superset ${r.superset_group}` : ''}`;
}

/** Next row to open: the first unfinished one after `from`, wrapping around; null when all are done. */
export function nextOpenRow(rowsDone: boolean[], from: number): number | null {
  for (let i = 1; i <= rowsDone.length; i++) {
    const j = (from + i) % rowsDone.length;
    if (!rowsDone[j]) return j;
  }
  return null;
}
