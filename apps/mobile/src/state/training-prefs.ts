import { create } from 'zustand';

import { kv } from '@/lib/storage';

const KEY = 'settings.training';

/** Rest preferences on this device (Profile › Training, and per exercise from the exercise card). */
export type TrainingPrefs = {
  restEnabled: boolean; // start the rest timer after each set
  cueSound: boolean; // 3-2-1 beeps for the rest and block timers (#80)
  restAdjust: number; // seconds added to every program rest (−30 … +30)
  supersetTransition: number; // rest between superset partners (0 = go straight to the next exercise)
  perExercise: Record<string, number>; // exercise slug → your own rest in seconds
  emomLevel: number; // L1 = 0, L2 = 1, L3 = 2: picked per session, remembered for the next one
  bands: string[]; // your resistance bands for X3 sets, lightest first
  lastBand: Record<string, string>; // exercise slug → the band used last time
};

export const DEFAULT_BANDS = ['White', 'Light gray', 'Dark gray', 'Black', 'Orange'];

export const DEFAULT_PREFS: TrainingPrefs = {
  restEnabled: true,
  cueSound: true,
  restAdjust: 0,
  supersetTransition: 0,
  perExercise: {},
  emomLevel: 0,
  bands: DEFAULT_BANDS,
  lastBand: {},
};

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
    const { restEnabled, cueSound, restAdjust, supersetTransition, perExercise, emomLevel, bands, lastBand } = get();
    kv.set(
      KEY,
      JSON.stringify({
        restEnabled,
        cueSound,
        restAdjust,
        supersetTransition,
        perExercise,
        emomLevel,
        bands,
        lastBand,
      }),
    );
  },
  setExerciseRest: (slug, seconds) => {
    const perExercise = { ...get().perExercise };
    if (seconds === null) delete perExercise[slug];
    else perExercise[slug] = seconds;
    get().set({ perExercise });
  },
}));
