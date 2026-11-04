import { create } from 'zustand';

import { kv } from '@/lib/storage';

const KEY = 'settings.training';

/** Rest preferences on this device (Profile › Training, and per exercise from the exercise card). */
export type TrainingPrefs = {
  restEnabled: boolean; // start the rest timer after each set
  restAdjust: number; // seconds added to every program rest (−30 … +30)
  supersetTransition: number; // rest between superset partners (0 = go straight to the next exercise)
  perExercise: Record<string, number>; // exercise slug → your own rest in seconds
};

export const DEFAULT_PREFS: TrainingPrefs = { restEnabled: true, restAdjust: 0, supersetTransition: 0, perExercise: {} };

function load(): TrainingPrefs {
  try {
    const raw = kv.get(KEY);
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS;
  }
}

type State = TrainingPrefs & {
  set: (patch: Partial<TrainingPrefs>) => void;
  setExerciseRest: (slug: string, seconds: number | null) => void;
};

export const useTrainingPrefs = create<State>((set, get) => ({
  ...load(),
  set: (patch) => {
    set(patch);
    const { restEnabled, restAdjust, supersetTransition, perExercise } = get();
    kv.set(KEY, JSON.stringify({ restEnabled, restAdjust, supersetTransition, perExercise }));
  },
  setExerciseRest: (slug, seconds) => {
    const perExercise = { ...get().perExercise };
    if (seconds === null) delete perExercise[slug];
    else perExercise[slug] = seconds;
    get().set({ perExercise });
  },
}));
