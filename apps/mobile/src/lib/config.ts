import Constants from 'expo-constants';
import { Platform } from 'react-native';

export const API_PORT = 8000;

/**
 * Where the API lives by default. In development the API runs on the same PC as the Expo dev server
 * (`docker compose --profile full up`), so the phone reaches it at the dev server's LAN address.
 * `EXPO_PUBLIC_API_URL` overrides it, and so does the API URL setting in Profile.
 */
export function defaultApiUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, '');
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
  }
  const hostUri = Constants.expoConfig?.hostUri ?? Constants.platform?.hostUri;
  const host = hostUri?.split(':')[0];
  return `http://${host || 'localhost'}:${API_PORT}`;
}
