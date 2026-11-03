import KvStore from 'expo-sqlite/kv-store';
import { Platform } from 'react-native';

// During static rendering on the server there is no browser storage (Node only has an experimental stub).
const webStore = (): Storage | undefined => (typeof window === 'undefined' ? undefined : window.localStorage);

/**
 * Small synchronous key-value store for device settings (dev email, API URL).
 * Native: expo-sqlite's kv-store. Web: localStorage, so the web build needs no SQLite wasm for settings.
 */
export const kv = {
  get(key: string): string | null {
    try {
      if (Platform.OS === 'web') return webStore()?.getItem(key) ?? null;
      return KvStore.getItemSync(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string | null): void {
    try {
      if (Platform.OS === 'web') {
        if (value === null) webStore()?.removeItem(key);
        else webStore()?.setItem(key, value);
        return;
      }
      if (value === null) KvStore.removeItemSync(key);
      else KvStore.setItemSync(key, value);
    } catch {
      // Settings are a convenience; failing to persist one must not break the app.
    }
  },
};
