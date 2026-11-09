import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { useEffect, useRef } from 'react';
import { AppState, Platform } from 'react-native';

import { haptic } from '@/lib/feedback';
import { playCue, prepareSounds } from '@/lib/sounds';
import { cueAt, type Cue } from '@/lib/train';
import { cancelIntervalAlerts, scheduleIntervalAlerts, useIntervalTimer } from '@/state/interval';
import { setRestBackground, useRest } from '@/state/rest';
import { useTrainingPrefs } from '@/state/training-prefs';

const TAG = 'ki-forge-timer';
const native = Platform.OS !== 'web';

/** Beep (if on) and buzz for one cue. Exported for the rest timer's end. */
export function fireCue(cue: Cue): void {
  if (useTrainingPrefs.getState().cueSound) playCue(cue);
  if (cue === 'tick') haptic.set();
  else if (cue === 'go') haptic.restDone();
  else haptic.cleared();
}

/**
 * In-app timer cues (#80), mounted once under the tabs. While a block or rest timer runs it keeps the
 * screen on and plays the 3-2-1 / go / done cues on the wall clock. When the app leaves the foreground
 * the timers fall back to scheduled notifications; they are cancelled when it comes back.
 */
export function TimerCues() {
  const startedAt = useIntervalTimer((s) => s.startedAt);
  const block = useIntervalTimer((s) => s.block);
  const restEndsAt = useRest((s) => s.endsAt);
  const running = (startedAt != null && block != null) || restEndsAt != null;
  const lastBlockSecond = useRef<number | null>(null);
  const lastRestSecond = useRef<number | null>(null);

  // Keep the screen on while anything is counting.
  useEffect(() => {
    if (!running || !native) return;
    prepareSounds();
    void activateKeepAwakeAsync(TAG).catch(() => {});
    return () => void deactivateKeepAwake(TAG).catch(() => {});
  }, [running]);

  // Background: notifications take over. Foreground: in-app cues only.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      const away = state !== 'active';
      setRestBackground(away);
      if (away) void scheduleIntervalAlerts();
      else void cancelIntervalAlerts();
      lastBlockSecond.current = null; // don't replay cues that were missed while away
      lastRestSecond.current = null;
    });
    return () => sub.remove();
  }, []);

  useEffect(() => {
    lastBlockSecond.current = null;
    lastRestSecond.current = null;
    if (!running) return;
    const tick = () => {
      const now = Date.now();
      if (startedAt != null && block) {
        const t = Math.floor((now - startedAt) / 1000);
        const prev = lastBlockSecond.current;
        // Cue only on the next whole second (a jump means the app was paused: stay quiet and catch up).
        if (prev !== null && t === prev + 1) {
          const cue = cueAt(block, t);
          if (cue) fireCue(cue);
        }
        lastBlockSecond.current = t;
      }
      if (restEndsAt != null) {
        const left = Math.ceil((restEndsAt - now) / 1000);
        const prev = lastRestSecond.current;
        if (prev !== null && left === prev - 1 && left >= 1 && left <= 3) fireCue('tick');
        lastRestSecond.current = left;
      }
    };
    tick();
    const id = setInterval(tick, 100);
    return () => clearInterval(id);
  }, [running, startedAt, block, restEndsAt]);

  return null;
}
