import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { create } from 'zustand';

import { haptic } from '@/lib/feedback';
import { toast } from '@/state/toast';

/**
 * The rest timer. It counts to a wall-clock end time, so it survives the app being backgrounded; a local
 * notification fires at the end in case the app isn't open. +30 s and Skip reschedule or cancel it.
 */
type RestState = {
  endsAt: number | null; // epoch ms
  total: number; // seconds, for the ring
  start: (seconds: number) => void;
  extend: (seconds: number) => void;
  skip: () => void;
  finish: () => void;
};

const native = Platform.OS !== 'web';
let notificationId: string | null = null;
let permissionAsked = false;

async function schedule(endsAt: number): Promise<void> {
  if (!native) return;
  await cancel();
  try {
    if (!permissionAsked) {
      permissionAsked = true;
      if (Platform.OS === 'android') {
        await Notifications.setNotificationChannelAsync('rest-timer', {
          name: 'Rest timer',
          // eslint-disable-next-line import/namespace -- re-exported enum the import plugin cannot see
          importance: Notifications.AndroidImportance.HIGH,
        });
      }
      const current = await Notifications.getPermissionsAsync();
      if (!current.granted) await Notifications.requestPermissionsAsync();
    }
    const seconds = Math.max(1, Math.round((endsAt - Date.now()) / 1000));
    notificationId = await Notifications.scheduleNotificationAsync({
      content: { title: 'Rest done', body: 'Next set.', sound: true },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL, seconds, channelId: 'rest-timer' },
    });
  } catch {
    // No permission or no support: the in-app countdown still works.
  }
}

async function cancel(): Promise<void> {
  if (!native || !notificationId) return;
  const id = notificationId;
  notificationId = null;
  await Notifications.cancelScheduledNotificationAsync(id).catch(() => {});
}

export const useRest = create<RestState>((set, get) => ({
  endsAt: null,
  total: 0,
  start: (seconds) => {
    const endsAt = Date.now() + seconds * 1000;
    set({ endsAt, total: seconds });
    void schedule(endsAt);
  },
  extend: (seconds) => {
    const { endsAt, total } = get();
    if (!endsAt) return;
    const next = endsAt + seconds * 1000;
    set({ endsAt: next, total: total + seconds });
    void schedule(next);
  },
  skip: () => {
    set({ endsAt: null, total: 0 });
    void cancel();
  },
  finish: () => {
    if (!get().endsAt) return;
    set({ endsAt: null, total: 0 });
    void cancel(); // already shown in-app; don't also notify
    haptic.restDone();
    toast('Rest done. Next set.');
  },
}));

/** Show rest notifications as banners even while the app is open in the background. */
export function configureNotifications(): void {
  if (!native) return;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}
