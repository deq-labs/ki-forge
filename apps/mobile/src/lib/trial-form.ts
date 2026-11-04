/**
 * Trial form helpers: groups, parsing and the row's mm:ss format. Display and input only: Power Level,
 * frame ratio and completion come from the server (CLAUDE.md rule 1).
 */

export type TestField = { type: string; label: string; unit: string; placeholder: string };
export type TestGroup = { title: string; fields: TestField[] };

/** The 9 tests in the screen spec's groups (docs/06-screens.md, Trial entry). */
export const GROUPS: TestGroup[] = [
  {
    title: 'Strength',
    fields: [
      { type: 'press_5rm_lb', label: 'Overhead press 5RM', unit: 'lb', placeholder: '115' },
      { type: 'squat_5rm_lb', label: 'Back squat 5RM', unit: 'lb', placeholder: '185' },
      { type: 'deadlift_5rm_lb', label: 'Deadlift 5RM', unit: 'lb', placeholder: '245' },
    ],
  },
  {
    title: 'Bodyweight',
    fields: [
      { type: 'pullups_max', label: 'Strict pull-ups', unit: 'reps', placeholder: '8' },
      { type: 'pushups_max', label: 'Push-ups', unit: 'reps', placeholder: '30' },
    ],
  },
  { title: 'Engine', fields: [{ type: 'row_2k_seconds', label: '2,000 m row', unit: 'mm:ss', placeholder: '8:30' }] },
  {
    title: 'Body',
    fields: [
      { type: 'bodyweight_lb', label: 'Bodyweight', unit: 'lb', placeholder: '190' },
      { type: 'shoulders_in', label: 'Shoulders', unit: 'in', placeholder: '45.5' },
      { type: 'waist_in', label: 'Waist', unit: 'in', placeholder: '34' },
    ],
  },
];

export const ALL_TESTS = GROUPS.flatMap((g) => g.fields.map((f) => f.type));

/** "8:30" → 510; "510" → 510; "" → null; invalid → undefined. */
export function parseRow(text: string): number | null | undefined {
  const t = text.trim();
  if (!t) return null;
  const m = /^(\d{1,2}):([0-5]\d)$/.exec(t);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  if (/^\d{2,4}$/.test(t)) return Number(t);
  return undefined;
}

export function formatRow(seconds: number | null | undefined): string {
  if (seconds == null) return '';
  return `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
}

/** A plain number field: "" → null; "45.5" or "45,5" → 45.5; invalid or negative → undefined. */
export function parseNumber(text: string): number | null | undefined {
  const t = text.trim().replace(',', '.');
  if (!t) return null;
  if (!/^\d+(\.\d+)?$/.test(t)) return undefined;
  return Number(t);
}

export function parseField(type: string, text: string): number | null | undefined {
  return type === 'row_2k_seconds' ? parseRow(text) : parseNumber(text);
}

export function formatField(type: string, value: number | null | undefined): string {
  if (value == null) return '';
  return type === 'row_2k_seconds' ? formatRow(value) : String(value);
}

/** The Trial week schedule (docs/06-screens.md, Trial entry; the workbook's Week 0 schedule). */
export type TrialDay = { key: string; day: string; what: string; tests: string[] };

export const TRIAL_DAYS: TrialDay[] = [
  {
    key: 'mon',
    day: 'Mon',
    what: 'Morning: bodyweight, shoulders, waist. Evening: max pull-ups, then max push-ups.',
    tests: ['bodyweight_lb', 'shoulders_in', 'waist_in', 'pullups_max', 'pushups_max'],
  },
  { key: 'tue', day: 'Tue', what: 'Back squat: work up to a 5-rep max with good form, 1 rep left in the tank.', tests: ['squat_5rm_lb'] },
  { key: 'wed', day: 'Wed', what: 'Rest or an easy walk. Weigh in again.', tests: [] },
  { key: 'thu', day: 'Thu', what: 'Overhead press 5RM, then the 2,000 m row (damper 4–6).', tests: ['press_5rm_lb', 'row_2k_seconds'] },
  {
    key: 'fri',
    day: 'Fri',
    what: 'Deadlift 5RM. Weigh in again and enter the 3-morning bodyweight average.',
    tests: ['deadlift_5rm_lb', 'bodyweight_lb'],
  },
];

export function fieldOf(type: string): TestField | undefined {
  return GROUPS.flatMap((g) => g.fields).find((f) => f.type === type);
}
