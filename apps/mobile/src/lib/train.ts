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

export type LoggedLike = { exercise_slug: string; reps: number | null; weight_lb: number; set_no: number };

/**
 * Logged sets for a row: its exercise, the one a swapped row replaces, or any of a technique's progression
 * steps (matches the server's scoring).
 */
export function setsForRow<T extends LoggedLike>(
  row: Pick<Row, 'exercise' | 'swap' | 'is_swap' | 'steps'>,
  sets: T[],
): T[] {
  const steps = new Set(row.steps?.map((s) => s.exercise));
  return sets.filter(
    (s) => s.exercise_slug === row.exercise || (row.is_swap && s.exercise_slug === row.swap) || steps.has(s.exercise_slug),
  );
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
  const rowsDone = rows.map((r) => setsForRow(r, sets).length >= r.sets);
  const done = rows.reduce((n, r) => n + Math.min(r.sets, setsForRow(r, sets).length), 0);
  return { done, needed: rows.reduce((n, r) => n + r.sets, 0), rowsDone };
}

/** Rest after a set: the prescription's rest (90 s default), or 120 s after an exercise's last set. */
export function restSeconds(row: Pick<Row, 'rest_seconds' | 'sets'>, setsDoneAfter: number): number {
  if (setsDoneAfter >= row.sets) return 120;
  return row.rest_seconds && row.rest_seconds > 0 ? row.rest_seconds : 90;
}

/** "4 × 6–8 · superset A" */
export function prescriptionLine(r: Pick<Row, 'sets' | 'rep_min' | 'rep_max' | 'superset_group'>): string {
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
