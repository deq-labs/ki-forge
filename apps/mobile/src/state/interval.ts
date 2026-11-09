import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { create } from 'zustand';

import { blockSeconds, LEAD_IN_SECONDS, type BlockInfo } from '@/lib/train';
import { prepareTimerAlerts } from '@/state/rest';

/**
 * The interval timer for an EMOM, "every N:NN" or for-time block. Like the rest timer it counts from a
 * wall-clock start, so it keeps time with the screen off. Cues (3-2-1 beeps, "go", vibration) play in the
 * app (`TimerCues`); notifications are only a fallback while the app is in the background, because they
 * arrive late on Android (#80).
 */
type IntervalTimer = {
  key: string | null; // which block (session code + row key)
  startedAt: number | null; // epoch ms of the first interval; Start sets it LEAD_IN_SECONDS ahead
  block: BlockInfo | null;
  labels: string[]; // the movement names at the chosen level, for cues and notifications
  start: (key: string, block: BlockInfo, labels: string[]) => void;
  stop: () => void;
};

const native = Platform.OS !== 'web';
let scheduled: string[] = [];

export async function cancelIntervalAlerts(): Promise<void> {
  const ids = scheduled;
  scheduled = [];
  if (!native) return;
  await Promise.all(ids.map((id) => Notifications.cancelScheduledNotificationAsync(id).catch(() => {})));
}

/**
 * The app went to the background: schedule a notification for each interval change still to come
 * ("Minute 4 · Chest-to-bar pull-up", then "EMOM done"). Cancelled when the app comes back.
 */
export async function scheduleIntervalAlerts(): Promise<void> {
  const { block, labels, startedAt } = useIntervalTimer.getState();
  if (!native || !block || startedAt == null) return;
  await cancelIntervalAlerts();
  try {
    if (!(await Notifications.getPermissionsAsync()).granted) return; // asked at Start
    const elapsed = (Date.now() - startedAt) / 1000;
    const total = blockSeconds(block);
    const step = block.kind === 'for_time' || !block.interval_seconds ? 0 : block.interval_seconds;
    const n = block.kind === 'emom' ? Math.max(1, block.movements.length) : 1;
    const marks: { at: number; title: string; body: string }[] = [];
    if (elapsed < 0) marks.push({ at: 0, title: block.name, body: `Go: ${labels[0] ?? ''}` });
    for (let i = 1; step && i * step < total; i++) {
      marks.push(
        block.kind === 'emom'
          ? { at: i * step, title: `Minute ${i + 1}`, body: labels[i % n] ?? '' }
          : { at: i * step, title: `Round ${i + 1}`, body: 'Go.' },
      );
    }
    if (total)
      marks.push({
        at: total,
        title: block.kind === 'for_time' ? 'Time cap' : `${block.name} done`,
        body: 'Your rounds are logged.',
      });
    for (const m of marks.filter((x) => x.at > elapsed).slice(0, 60)) {
      const id = await Notifications.scheduleNotificationAsync({
        content: { title: m.title, body: m.body, sound: true },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
          seconds: Math.max(1, Math.round(m.at - elapsed)),
          channelId: 'rest-timer',
        },
      });
      scheduled.push(id);
    }
  } catch {
    // No permission or no support: the in-app cues still work once the app is open again.
  }
}

export const useIntervalTimer = create<IntervalTimer>((set) => ({
  key: null,
  startedAt: null,
  block: null,
  labels: [],
  start: (key, block, labels) => {
    set({ key, block, labels, startedAt: Date.now() + LEAD_IN_SECONDS * 1000 });
    void prepareTimerAlerts();
  },
  stop: () => {
    set({ key: null, block: null, labels: [], startedAt: null });
    void cancelIntervalAlerts();
  },
}));
