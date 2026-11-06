import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { create } from 'zustand';

import { blockSeconds, type BlockInfo } from '@/lib/train';

/**
 * The interval timer for an EMOM, "every N:NN" or for-time block. Like the rest timer it counts from a
 * wall-clock start, so it keeps time with the screen off; each interval change is also scheduled as a
 * local notification (sound and lock screen) and cancelled on stop.
 */
type IntervalTimer = {
  key: string | null; // which block (session code + row key)
  startedAt: number | null; // epoch ms
  block: BlockInfo | null;
  start: (key: string, block: BlockInfo, labels: string[]) => void;
  stop: () => void;
};

const native = Platform.OS !== 'web';
let scheduled: string[] = [];

async function cancelAll(): Promise<void> {
  const ids = scheduled;
  scheduled = [];
  if (!native) return;
  await Promise.all(ids.map((id) => Notifications.cancelScheduledNotificationAsync(id).catch(() => {})));
}

/** One notification per interval change: "Minute 4 · Chest-to-bar pull-up", then "EMOM done". */
async function scheduleBoundaries(block: BlockInfo, labels: string[]): Promise<void> {
  if (!native) return;
  await cancelAll();
  try {
    const current = await Notifications.getPermissionsAsync();
    if (!current.granted && !(await Notifications.requestPermissionsAsync()).granted) return;
    const total = blockSeconds(block);
    const step = block.kind === 'for_time' || !block.interval_seconds ? 0 : block.interval_seconds;
    const n = block.kind === 'emom' ? Math.max(1, block.movements.length) : 1;
    const marks: { at: number; title: string; body: string }[] = [];
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
        body: 'Log your rounds.',
      });
    for (const m of marks.slice(0, 60)) {
      scheduled.push(
        await Notifications.scheduleNotificationAsync({
          content: { title: m.title, body: m.body, sound: true },
          trigger: {
            type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
            seconds: m.at,
            channelId: 'rest-timer',
          },
        }),
      );
    }
  } catch {
    // No permission or no support: the in-app timer still works.
  }
}

export const useIntervalTimer = create<IntervalTimer>((set) => ({
  key: null,
  startedAt: null,
  block: null,
  start: (key, block, labels) => {
    set({ key, block, startedAt: Date.now() });
    void scheduleBoundaries(block, labels);
  },
  stop: () => {
    set({ key: null, block: null, startedAt: null });
    void cancelAll();
  },
}));
