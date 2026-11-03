import { create } from 'zustand';

import type { PathSlug } from '@/theme/tokens';

/** Choices made during onboarding, kept until the run is created. */
type Draft = {
  units: 'imperial' | 'metric';
  path: PathSlug;
  setUnits: (u: 'imperial' | 'metric') => void;
  setPath: (p: PathSlug) => void;
};

export const useOnboarding = create<Draft>((set) => ({
  units: 'imperial',
  path: 'storm',
  setUnits: (units) => set({ units }),
  setPath: (path) => set({ path }),
}));

/** Display units → storage units (CLAUDE.md rule 4: the DB stores lb and inches). */
export const KG_PER_LB = 0.45359237;
export const toLb = (value: number, units: 'imperial' | 'metric') =>
  units === 'metric' ? Math.round((value / KG_PER_LB) * 10) / 10 : value;
