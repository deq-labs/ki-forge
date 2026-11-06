import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { FormCues, Stepper, type FormInfo } from '@/components/exercise-card';
import { KText } from '@/components/k-text';
import type { LocalSet } from '@/db/repo';
import { haptic } from '@/lib/feedback';
import {
  blockSeconds,
  intervalState,
  levelOf,
  nextRound,
  prescriptionLine,
  roundsLogged,
  targetLine,
  type Level,
  type Row,
} from '@/lib/train';
import { SET_XP } from '@/lib/xp';
import { useIntervalTimer } from '@/state/interval';
import { useTrainingPrefs } from '@/state/training-prefs';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** One movement of a round as logged: the exercise done, the amount (reps, cal, steps or seconds) and load. */
export type RoundEntry = {
  exercise: string;
  amount: number;
  unit: string; // reps | cal | steps | seconds
  weight_lb: number;
  split_seconds?: number | null; // for time: when this round was finished
};

type Props = {
  row: Row;
  number: number;
  sets: LocalSet[];
  expanded: boolean;
  /** Unique per session and row, so only one block's timer runs at a time. */
  timerKey: string;
  load: (lb: number) => string;
  incrementOf: (slug: string) => number;
  formOf?: (slug: string) => FormInfo | undefined;
  onToggle: () => void;
  onLogRound: (round: number, entries: RoundEntry[]) => void;
};

const KIND_LABEL: Record<string, string> = {
  emom: 'EMOM',
  interval: 'Intervals',
  for_time: 'For time',
  circuit: 'Circuit',
};
const ROLE_LABEL: Record<string, string> = { main: 'Main', finisher: 'Finisher', core: 'Core', pump: 'Pump' };

function mmss(s: number): string {
  return `${Math.floor(s / 60)}:${String(Math.max(0, s) % 60).padStart(2, '0')}`;
}

function defaults(row: Row, level: number): RoundEntry[] {
  return row.block!.movements.map((m) => {
    const l = levelOf(m, level);
    return { exercise: l.exercise, amount: l.amount ?? 0, unit: l.unit, weight_lb: l.weight_lb ?? 0 };
  });
}

/**
 * A block of timed work (EMOM, "every 2:30", for time, circuit): pick L1/L2/L3, see each movement's target
 * and load, run the interval timer, and log a whole round with one tap (each movement editable first).
 */
export function BlockCard({
  row,
  number,
  sets,
  expanded,
  timerKey,
  load,
  incrementOf,
  formOf,
  onToggle,
  onLogRound,
}: Props) {
  const { colors } = useTheme();
  const block = row.block!;
  const level = useTrainingPrefs((s) => s.emomLevel);
  const setPrefs = useTrainingPrefs((s) => s.set);
  const hasLevels = block.movements.some((m) => m.levels.length > 1);
  const lvl = hasLevels ? level : 0;
  const done = roundsLogged(row, sets);
  const next = nextRound(row, sets);
  const cleared = done.length >= row.sets;

  // The round about to be logged; reset to the targets when the level or round changes.
  const [entries, setEntries] = useState<RoundEntry[]>(() => defaults(row, lvl));
  const [entriesFor, setEntriesFor] = useState(`${lvl}:${next}`);
  if (entriesFor !== `${lvl}:${next}`) {
    setEntriesFor(`${lvl}:${next}`);
    setEntries(defaults(row, lvl));
  }
  const [editing, setEditing] = useState(false);
  const [formFor, setFormFor] = useState<string | null>(null);
  const timer = useIntervalTimer();
  const forTimeRunning = block.kind === 'for_time' && timer.key === timerKey && timer.startedAt != null;
  const result = forTimeResult(row, sets);
  const missingLoad = block.movements.some((m) => {
    const l = levelOf(m, lvl);
    return l.percent != null && l.weight_lb == null;
  });

  const meta = [KIND_LABEL[block.kind] ?? block.kind, prescriptionLine(row), `${done.length}/${row.sets} rounds`].join(
    ' · ',
  );

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: colors.panel,
          borderColor: cleared ? colors.good : colors.line,
          borderWidth: cleared ? 2 : 1,
        },
      ]}>
      <Pressable
        onPress={onToggle}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        accessibilityLabel={`${block.name}, ${meta}${cleared ? ', cleared' : ''}`}
        style={styles.head}>
        <View style={[styles.num, { backgroundColor: cleared ? colors.good : colors.panelRaised }]}>
          <KText variant="bodyStrong" color={cleared ? 'night900' : 'inkMuted'}>
            {cleared ? '✓' : number}
          </KText>
        </View>
        <View style={styles.title}>
          <View style={styles.nameRow}>
            <KText variant="bodyStrong">{block.name}</KText>
            {row.role && ROLE_LABEL[row.role] ? (
              <View style={[styles.tag, { borderColor: colors.kiHot }]}>
                <KText variant="label" color="kiHot" style={styles.tagText}>
                  {ROLE_LABEL[row.role]}
                </KText>
              </View>
            ) : null}
          </View>
          <KText variant="caption" color="inkMuted">
            {meta}
          </KText>
        </View>
      </Pressable>

      {expanded && (
        <View style={styles.body}>
          {row.note ? (
            <KText variant="caption" color="inkMuted">
              {row.note}
            </KText>
          ) : null}
          {hasLevels && (
            <View style={styles.levels} accessibilityRole="radiogroup" accessibilityLabel="Level">
              {[0, 1, 2].map((i) => {
                const on = i === lvl;
                return (
                  <Pressable
                    key={i}
                    onPress={() => setPrefs({ emomLevel: i })}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: on }}
                    accessibilityLabel={`Level ${i + 1}`}
                    style={[
                      styles.level,
                      {
                        borderColor: on ? colors.ki : colors.line,
                        backgroundColor: on ? colors.panelRaised : colors.night800,
                      },
                    ]}>
                    <KText variant="bodyStrong" color={on ? 'kiHot' : 'inkMuted'}>
                      L{i + 1}
                    </KText>
                  </Pressable>
                );
              })}
            </View>
          )}

          <Timer row={row} timerKey={timerKey} level={lvl} />

          <View style={styles.moves}>
            {block.movements.map((m, i) => {
              const l: Level = levelOf(m, lvl);
              return (
                <View key={m.exercise + i} style={[styles.move, { borderColor: colors.line }]}>
                  <View style={styles.moveHead}>
                    <KText variant="label" color="inkMuted" style={styles.moveTag}>
                      {block.kind === 'emom' ? `Min ${i + 1}` : `${i + 1}`}
                    </KText>
                    <Pressable
                      onPress={() => setFormFor(formFor === l.exercise ? null : l.exercise)}
                      accessibilityRole="button"
                      accessibilityLabel={`${l.name}. ${targetLine(l, load)}. Show form cues`}
                      style={styles.flex}>
                      <KText variant="bodyStrong">{l.name}</KText>
                      <KText variant="dataSm" color="kiHot">
                        {targetLine(l, load)}
                      </KText>
                      {m.note ? (
                        <KText variant="caption" color="inkMuted">
                          {m.note}
                        </KText>
                      ) : null}
                    </Pressable>
                  </View>
                  {formFor === l.exercise && (
                    <FormCues info={formOf?.(l.exercise)} open onToggle={() => setFormFor(null)} />
                  )}
                </View>
              );
            })}
          </View>
          {missingLoad && (
            <KText variant="caption" color="volt">
              Enter your 1-rep maxes in Profile to see the loads.
            </KText>
          )}

          <View style={styles.rounds} accessibilityLabel={`${done.length} of ${row.sets} rounds logged`}>
            {Array.from({ length: block.rounds }, (_, i) => i + 1).map((n) => {
              const on = done.includes(n);
              return (
                <View
                  key={n}
                  style={[
                    styles.round,
                    {
                      borderColor: on ? colors.good : n === next ? colors.ki : colors.line,
                      backgroundColor: on ? colors.good : 'transparent',
                    },
                  ]}>
                  <KText variant="dataSm" color={on ? 'night900' : n === next ? 'kiHot' : 'inkMuted'}>
                    {on ? '✓' : n}
                  </KText>
                </View>
              );
            })}
          </View>

          {next !== null && editing && (
            <View style={styles.edit}>
              {entries.map((e, i) => {
                const l = levelOf(block.movements[i], lvl);
                const unit =
                  l.unit === 'cal' ? 'cal' : l.unit === 'steps' ? 'steps' : l.unit === 'seconds' ? 's' : 'reps';
                return (
                  <View key={i} style={styles.editRow}>
                    <KText variant="caption" color="inkMuted">
                      {l.name}
                    </KText>
                    <View style={styles.steppers}>
                      <Stepper
                        value={e.amount}
                        unit={unit}
                        step={l.unit === 'seconds' ? 5 : 1}
                        min={0}
                        label={unit}
                        onChange={(v) => setEntries((xs) => xs.map((x, j) => (j === i ? { ...x, amount: v } : x)))}
                      />
                      {(l.weight_lb != null || l.percent != null) && (
                        <Stepper
                          value={e.weight_lb}
                          unit="lb"
                          step={incrementOf(l.exercise) || 5}
                          min={0}
                          label="Weight"
                          onChange={(v) => setEntries((xs) => xs.map((x, j) => (j === i ? { ...x, weight_lb: v } : x)))}
                        />
                      )}
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {result ? (
            <KText variant="bodyStrong" color="good">
              {result}
            </KText>
          ) : null}
          {next !== null ? (
            <View style={styles.actions}>
              <Pressable
                onPress={() => {
                  // For time: each round keeps the time it was finished at; the last one is your result.
                  const split = forTimeRunning ? Math.round((Date.now() - timer.startedAt!) / 1000) : null;
                  onLogRound(
                    next,
                    entries.map((e) => ({ ...e, split_seconds: split })),
                  );
                  if (forTimeRunning && next === block.rounds) timer.stop();
                  setEditing(false);
                }}
                accessibilityRole="button"
                style={({ pressed }) => [styles.log, { backgroundColor: colors.ink, opacity: pressed ? 0.85 : 1 }]}>
                <KText variant="cardTitle" color="night900">
                  Log round {next} · +{SET_XP} XP
                </KText>
              </Pressable>
              <Pressable onPress={() => setEditing((v) => !v)} accessibilityRole="button" style={styles.editBtn}>
                <KText variant="caption" color="volt">
                  {editing ? 'Use the targets' : 'Change reps or load for this round'}
                </KText>
              </Pressable>
            </View>
          ) : (
            <KText variant="caption" color="good">
              ✓ All {block.rounds} rounds logged.
            </KText>
          )}
        </View>
      )}
    </View>
  );
}

/** "5 rounds in 12:34", or "3 rounds by 15:00 (capped)": the for-time result from the logged splits. */
export function forTimeResult(row: Row, sets: LocalSet[]): string | null {
  const block = row.block;
  if (block?.kind !== 'for_time') return null;
  const rounds = roundsLogged(row, sets);
  const splits = sets.filter((s) => s.slot === row.key && s.seconds != null).map((s) => s.seconds!);
  if (!rounds.length || !splits.length) return null;
  const last = Math.max(...splits);
  if (rounds.length >= block.rounds) return `${block.rounds} rounds in ${mmss(last)}`;
  const cap = block.cap_seconds ?? 0;
  return cap && last >= cap
    ? `${rounds.length} rounds by ${mmss(cap)} (capped)`
    : `${rounds.length} rounds at ${mmss(last)}`;
}

/** The interval timer: which minute and movement is up, time left, and the round; buzzes on each change. */
function Timer({ row, timerKey, level }: { row: Row; timerKey: string; level: number }) {
  const { colors } = useTheme();
  const block = row.block!;
  const { key, startedAt, start, stop } = useIntervalTimer();
  const running = key === timerKey && startedAt != null;
  const [now, setNow] = useState(() => Date.now());
  const lastSlot = useRef<string | null>(null);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [running]);

  const state = running ? intervalState(block, Math.max(0, (now - startedAt!) / 1000)) : null;
  const slotId = state ? `${state.round}:${state.movement}:${state.finished}` : null;
  useEffect(() => {
    if (!slotId) {
      lastSlot.current = null;
      return;
    }
    if (lastSlot.current && lastSlot.current !== slotId) haptic.restDone();
    lastSlot.current = slotId;
  }, [slotId]);

  if (block.kind === 'circuit') return null; // at your own pace; rest between rounds uses the rest timer
  const total = blockSeconds(block);
  const labels = block.movements.map((m) => levelOf(m, level).name);

  if (!running || !state) {
    return (
      <Pressable
        onPress={() => start(timerKey, block, labels)}
        accessibilityRole="button"
        style={[styles.timerBtn, { borderColor: colors.volt }]}>
        <KText variant="bodyStrong" color="volt">
          ▶ Start {block.kind === 'for_time' ? `${mmss(total)} cap` : `${mmss(total)} timer`}
        </KText>
      </Pressable>
    );
  }

  const up =
    state.movement != null
      ? labels[state.movement]
      : block.kind === 'for_time'
        ? 'All rounds, as fast as you can'
        : 'Every movement this interval';
  return (
    <View
      style={[styles.timer, { borderColor: colors.volt, backgroundColor: colors.night800 }]}
      accessibilityRole="timer"
      accessibilityLiveRegion="polite"
      accessibilityLabel={
        state.finished ? 'Time' : `${up}. ${mmss(state.secondsLeft)} left. Round ${state.round} of ${block.rounds}`
      }>
      {state.finished ? (
        <KText variant="cardTitle" color="good">
          {block.kind === 'for_time' ? 'Time cap. Log your rounds.' : 'Done. Log your rounds.'}
        </KText>
      ) : (
        <>
          <KText variant="label" color="inkMuted">
            {block.kind === 'emom'
              ? `Minute ${Math.floor(state.elapsed / (block.interval_seconds ?? 60)) + 1} of ${Math.round(total / 60)} · Round ${state.round}/${block.rounds}`
              : block.kind === 'for_time'
                ? `${mmss(state.elapsed)} elapsed`
                : `Round ${state.round}/${block.rounds}`}
          </KText>
          <KText variant="burst" color="volt">
            {block.kind === 'for_time' ? mmss(state.elapsed) : mmss(state.secondsLeft)}
          </KText>
          <KText variant="bodyStrong">{up}</KText>
        </>
      )}
      <Pressable
        onPress={stop}
        accessibilityRole="button"
        style={[styles.stop, { backgroundColor: colors.panelRaised }]}>
        <KText variant="bodyStrong">{state.finished ? 'Close timer' : 'Stop'}</KText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, overflow: 'hidden' },
  head: { flexDirection: 'row', alignItems: 'center', gap: spacing[3], padding: spacing[4], minHeight: 64 },
  num: { width: 40, height: 40, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, gap: 2 },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: spacing[2], flexWrap: 'wrap' },
  tag: { borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 1 },
  tagText: { fontSize: 9, lineHeight: 12 },
  body: { paddingHorizontal: spacing[4], paddingBottom: spacing[4], gap: spacing[3] },
  flex: { flex: 1 },
  levels: { flexDirection: 'row', gap: spacing[2] },
  level: {
    flex: 1,
    minHeight: 44,
    borderRadius: radius.md,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  moves: { gap: spacing[2] },
  move: { borderWidth: 1, borderRadius: radius.md, padding: spacing[3], gap: spacing[2] },
  moveHead: { flexDirection: 'row', gap: spacing[3], alignItems: 'flex-start' },
  moveTag: { width: 44, paddingTop: 2 },
  rounds: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  round: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  edit: { gap: spacing[3] },
  editRow: { gap: spacing[1] },
  steppers: { flexDirection: 'row', gap: spacing[3] },
  actions: { gap: spacing[2] },
  log: {
    minHeight: 52,
    borderRadius: radius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing[3],
  },
  editBtn: { alignSelf: 'center', minHeight: 44, justifyContent: 'center', paddingHorizontal: spacing[3] },
  timerBtn: {
    minHeight: 48,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  timer: { borderWidth: 1.5, borderRadius: radius.lg, padding: spacing[4], gap: spacing[2], alignItems: 'center' },
  stop: {
    minHeight: 44,
    minWidth: 120,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing[2],
  },
});
