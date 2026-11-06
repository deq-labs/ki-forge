import { create } from 'zustand';

import { defaultApiUrl } from '@/lib/config';
import { kv } from '@/lib/storage';
import { themeColors, type ThemeId } from '@/theme/tokens';

const DEV_EMAIL = 'settings.devEmail';
const API_URL = 'settings.apiUrl';
const GARAGE = 'settings.garage';
const THEME = 'settings.theme';

const storedTheme = (): ThemeId => {
  const v = kv.get(THEME);
  return v && v in themeColors ? (v as ThemeId) : 'night';
};

type SettingsState = {
  /** Who is signed in. Until Clerk (M6) this is a dev identity sent as `X-Dev-User` to the local API. */
  devEmail: string | null;
  /** Override for the API base URL; null = the default (the dev server's LAN address). */
  apiUrlOverride: string | null;
  /** Garage mode for this device (HUD toggle); null = the run's garage default. */
  garage: boolean | null;
  setGarage: (on: boolean) => void;
  /** Color theme for this device (Profile › Theme). */
  theme: ThemeId;
  setTheme: (id: ThemeId) => void;
  signIn: (email: string) => void;
  signOut: () => void;
  setApiUrl: (url: string | null) => void;
};

export const useSettings = create<SettingsState>((set) => ({
  devEmail: kv.get(DEV_EMAIL),
  apiUrlOverride: kv.get(API_URL),
  garage: kv.get(GARAGE) === null ? null : kv.get(GARAGE) === '1',
  theme: storedTheme(),
  setTheme: (id) => {
    kv.set(THEME, id);
    set({ theme: id });
  },
  setGarage: (on) => {
    kv.set(GARAGE, on ? '1' : '0');
    set({ garage: on });
  },
  signIn: (email) => {
    const clean = email.trim().toLowerCase();
    kv.set(DEV_EMAIL, clean);
    set({ devEmail: clean });
  },
  signOut: () => {
    kv.set(DEV_EMAIL, null);
    set({ devEmail: null });
  },
  setApiUrl: (url) => {
    const clean = url?.trim().replace(/\/$/, '') || null;
    kv.set(API_URL, clean);
    set({ apiUrlOverride: clean });
  },
}));

export function apiUrl(): string {
  return useSettings.getState().apiUrlOverride ?? defaultApiUrl();
}

export function isEmail(v: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());
}
