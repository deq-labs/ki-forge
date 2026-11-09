import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { FormCues, Stepper, type FormInfo } from '@/components/exercise-card';
import { KText } from '@/components/k-text';
import type { LocalSet } from '@/db/repo';
import {
  blockSeconds,
  intervalState,
  levelOf,
  nextRound,
  prescriptionLine,
  roundSets,
  roundsFinished,
  roundsLogged,
  targetLine,
  upNext,
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
  /**
   * Log a round. `auto`: the timer logged it at its targets (no rest, the card stays open until the last
   * one). `replaces`: the round's existing sets, one per movement, when changing a logged round.
   */
  onLogRound: (round: number, entries: RoundEntry[], opts?: { auto?: boolean; replaces?: (LocalSet | undefined)[] }) => void;
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

/** A logged round as editable entries (movements missing from it get the targets). */
function fromLogged(row: Row, level: number, logged: (LocalSet | undefined)[]): RoundEntry[] {
  return defaults(row, level).map((d, i) => {
    const s = logged[i];
    if (!s) return d;
    const held = d.unit === 'seconds';
    return {
      exercise: s.exercise_slug,
      amount: (held ? s.seconds : s.reps) ?? d.amount,
      unit: d.unit,
      weight_lb: s.weight_lb,
      split_seconds: held ? null : (s.seconds ?? null),
    };
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
  // Changing a round that is already logged (e.g. one the timer logged at its targets).
  const [fix, setFix] = useState<{ round: number; entries: RoundEntry[] } | null>(null);
  const [formFor, setFormFor] = useState<string | null>(null);
  const timer = useIntervalTimer();
  const running = timer.key === timerKey && timer.startedAt != null;
  const forTimeRunning = block.kind === 'for_time' && running;

  // Auto-log (#80): each EMOM / "every N:NN" round is logged at its targets when its last interval ends,
  // also after coming back to the app. Rounds you logged yourself are left alone.
  const autoLogged = useRef(new Set<number>());
  const logFinished = () => {
    const { startedAt } = useIntervalTimer.getState();
    if (!running || startedAt == null) return;
    const elapsed = (Date.now() - startedAt) / 1000;
    const finished = roundsFinished(block, elapsed);
    for (let n = 1; n <= finished; n++) {
      if (done.includes(n) || autoLogged.current.has(n)) continue;
      autoLogged.current.add(n);
      onLogRound(n, n === next ? entries : defaults(row, lvl), { auto: true });
    }
    // Close the timer a moment after the end, once the "done" cue has played.
    const total = blockSeconds(block);
    if (block.kind !== 'for_time' && total && elapsed >= total + 2) timer.stop();
  };
  const onTick = useEffectEvent(logFinished);
  useEffect(() => {
    if (!running) return;
    autoLogged.current.clear();
    onTick();
    const id = setInterval(() => onTick(), 1000);
    return () => clearInterval(id);
  }, [running, timer.startedAt]);
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

          <Timer
            row={row}
            timerKey={timerKey}
            level={lvl}
            onStop={() => {
              logFinished(); // rounds whose time is up count, even if Stop beats the next check
              timer.stop();
            }}
          />

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
              const fixing = fix?.round === n;
              return (
                <Pressable
                  key={n}
                  disabled={!on}
                  onPress={() =>
                    setFix(fixing ? null : { round: n, entries: fromLogged(row, lvl, roundSets(row, sets, n)) })
                  }
                  accessibilityRole={on ? 'button' : undefined}
                  accessibilityLabel={on ? `Round ${n} logged. Change it` : `Round ${n}`}
                  accessibilityState={on ? { expanded: fixing } : undefined}
                  style={[
                    styles.round,
                    {
                      borderColor: fixing ? colors.volt : on ? colors.good : n === next ? colors.ki : colors.line,
                      backgroundColor: on ? colors.good : 'transparent',
                    },
                  ]}>
                  <KText variant="dataSm" color={on ? 'night900' : n === next ? 'kiHot' : 'inkMuted'}>
                    {on ? '✓' : n}
                  </KText>
                </Pressable>
              );
            })}
          </View>
          {done.length > 0 && !fix && (
            <KText variant="caption" color="inkMuted">
              {running && block.kind !== 'for_time'
                ? 'Rounds log themselves at the targets when their time is up. Tap a ✓ to change one.'
                : 'Tap a ✓ to change that round.'}
            </KText>
          )}

          {fix && (
            <View style={[styles.fix, { borderColor: colors.volt }]}>
              <KText variant="bodyStrong">Change round {fix.round}</KText>
              <RoundEditor
                row={row}
                level={lvl}
                entries={fix.entries}
                incrementOf={incrementOf}
                onChange={(entries) => setFix({ ...fix, entries })}
              />
              <View style={styles.fixActions}>
                <Pressable
                  onPress={() => {
                    onLogRound(fix.round, fix.entries, { replaces: roundSets(row, sets, fix.round) });
                    setFix(null);
                  }}
                  accessibilityRole="button"
                  style={({ pressed }) => [styles.log, styles.flex, { backgroundColor: colors.ink, opacity: pressed ? 0.85 : 1 }]}>
                  <KText variant="cardTitle" color="night900">
                    Save round {fix.round}
                  </KText>
                </Pressable>
                <Pressable onPress={() => setFix(null)} accessibilityRole="button" style={styles.editBtn}>
                  <KText variant="caption" color="volt">
                    Cancel
                  </KText>
                </Pressable>
              </View>
            </View>
          )}

          {next !== null && editing && (
            <RoundEditor row={row} level={lvl} entries={entries} incrementOf={incrementOf} onChange={setEntries} />
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

/** Reps (cal, steps, seconds) and load per movement for one round. */
function RoundEditor({
  row,
  level,
  entries,
  incrementOf,
  onChange,
}: {
  row: Row;
  level: number;
  entries: RoundEntry[];
  incrementOf: (slug: string) => number;
  onChange: (entries: RoundEntry[]) => void;
}) {
  const set = (i: number, patch: Partial<RoundEntry>) => onChange(entries.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <View style={styles.edit}>
      {entries.map((e, i) => {
        const l = levelOf(row.block!.movements[i], level);
        const unit = l.unit === 'cal' ? 'cal' : l.unit === 'steps' ? 'steps' : l.unit === 'seconds' ? 's' : 'reps';
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
                onChange={(v) => set(i, { amount: v })}
              />
              {(l.weight_lb != null || l.percent != null) && (
                <Stepper
                  value={e.weight_lb}
                  unit="lb"
                  step={incrementOf(l.exercise) || 5}
                  min={0}
                  label="Weight"
                  onChange={(v) => set(i, { weight_lb: v })}
                />
              )}
            </View>
          </View>
        );
      })}
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

/**
 * The interval timer: a 5 s "get ready", then which minute and movement is up and the time left. The last
 * 10 s preview what's next and the last 3 count down big (with beeps from `TimerCues`).
 */
function Timer({ row, timerKey, level, onStop }: { row: Row; timerKey: string; level: number; onStop: () => void }) {
  const { colors } = useTheme();
  const block = row.block!;
  const { key, startedAt, start } = useIntervalTimer();
  const running = key === timerKey && startedAt != null;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(t);
  }, [running]);

  if (block.kind === 'circuit') return null; // at your own pace; rest between rounds uses the rest timer
  const total = blockSeconds(block);
  const labels = block.movements.map((m) => levelOf(m, level).name);

  if (!running) {
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

  const raw = (now - startedAt!) / 1000;
  const leadIn = raw < 0 ? Math.ceil(-raw) : 0;
  const state = intervalState(block, Math.max(0, raw));
  const up =
    state.movement != null
      ? labels[state.movement]
      : block.kind === 'for_time'
        ? 'All rounds, as fast as you can'
        : 'Every movement this interval';
  const following = upNext(block, raw, labels);
  // Seconds to the next change: the interval's end, or the cap for time.
  const toChange = leadIn || state.secondsLeft;
  const countdown = !state.finished && toChange > 0 && toChange <= 3 ? toChange : null;

  return (
    <View
      style={[styles.timer, { borderColor: countdown ? colors.kiHot : colors.volt, backgroundColor: colors.night800 }]}
      accessibilityRole="timer"
      accessibilityLiveRegion="polite"
      accessibilityLabel={
        leadIn
          ? `Get ready. ${labels[0]} in ${leadIn}`
          : state.finished
            ? 'Time'
            : `${up}. ${mmss(state.secondsLeft)} left. Round ${state.round} of ${block.rounds}`
      }>
      {leadIn ? (
        <>
          <KText variant="label" color="inkMuted">
            Get ready
          </KText>
          <KText variant="burst" color="kiHot">
            {leadIn}
          </KText>
          <KText variant="bodyStrong">First: {block.kind === 'emom' ? labels[0] : up}</KText>
        </>
      ) : state.finished ? (
        <KText variant="cardTitle" color="good">
          {block.kind === 'for_time' ? 'Time cap. Log your rounds.' : 'Done. Every round is logged.'}
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
          <KText variant="burst" color={countdown ? 'kiHot' : 'volt'}>
            {countdown ?? (block.kind === 'for_time' ? mmss(state.elapsed) : mmss(state.secondsLeft))}
          </KText>
          <KText variant="bodyStrong">{up}</KText>
          {following && state.secondsLeft <= 10 ? (
            <KText variant="caption" color="volt">
              Next: {following}
            </KText>
          ) : null}
        </>
      )}
      <Pressable
        onPress={onStop}
        accessibilityRole="button"
        style={[styles.stop, { backgroundColor: colors.panelRaised }]}>
        <KText variant="bodyStrong">{state.finished && !leadIn ? 'Close timer' : 'Stop'}</KText>
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
  fix: { borderWidth: 1.5, borderRadius: radius.md, padding: spacing[3], gap: spacing[3] },
  fixActions: { flexDirection: 'row', alignItems: 'center', gap: spacing[2] },
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
