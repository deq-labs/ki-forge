import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withSequence, withTiming } from 'react-native-reanimated';

import { KText } from '@/components/k-text';
import { RestSetting } from '@/components/rest-setting';
import type { LocalSet } from '@/db/repo';
import { defaultStep, isDoneStyle, nextStep, prescriptionLine, setsForRow, type Row } from '@/lib/train';
import { SET_XP } from '@/lib/xp';
import { useTrainingPrefs } from '@/state/training-prefs';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** `exercise` is the technique step picked (else the row's exercise is logged). */
export type LogInput = { weight_lb: number; reps: number; supersedes?: LocalSet; exercise?: string; band?: string };

export type FormInfo = { name: string; setup?: string | null; cues?: string[] };

type Props = {
  row: Row;
  /** Setup and form cues for an exercise slug (from the cached program). */
  formOf?: (slug: string) => FormInfo | undefined;
  number: number;
  sets: LocalSet[]; // current (latest) sets of this session
  expanded: boolean;
  increment: number;
  garage: boolean;
  onToggle: () => void;
  onLog: (input: LogInput) => void;
};

/** One exercise: tap the header to expand; chips, weight and rep steppers, and the Log set button. */
export function ExerciseCard({ row, number, sets, expanded, increment, garage, onToggle, onLog, formOf }: Props) {
  const { colors } = useTheme();
  const mine = setsForRow(row, sets);
  const done = Math.min(mine.length, row.sets);
  const cleared = done >= row.sets;
  const doneStyle = isDoneStyle(row);
  const last = mine[mine.length - 1];

  // Technique progressions: pick the step for today (defaults to the one you're on).
  const [step, setStepState] = useState<string | null>(() => defaultStep(row));
  const stepInfo = row.steps?.find((s) => s.exercise === step);
  const upNext = row.ready_to_advance && step === row.current_step ? nextStep(row, step) : null;
  const [weight, setWeight] = useState(last?.weight_lb ?? stepInfo?.prefill_weight_lb ?? row.prefill_weight_lb ?? 0);
  const setStep = (slug: string) => {
    setStepState(slug);
    const lastOnStep = [...mine].reverse().find((s) => s.exercise_slug === slug);
    setWeight(lastOnStep?.weight_lb ?? row.steps?.find((s) => s.exercise === slug)?.prefill_weight_lb ?? 0);
  };
  const [reps, setReps] = useState(last?.reps ?? (row.role === 'x3' ? row.rep_min : row.rep_max));
  // X3 sets: band + reps to failure, no weight.
  const x3 = row.role === 'x3';
  const bands = useTrainingPrefs((s) => s.bands);
  const lastBand = useTrainingPrefs((s) => s.lastBand[row.exercise]);
  const [band, setBand] = useState<string | null>(last?.band ?? lastBand ?? null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditingState] = useState<LocalSet | null>(null);
  const setEditing = (s: LocalSet | null) => {
    setEditingState(s);
    if (s) {
      setWeight(s.weight_lb);
      setReps(s.reps ?? row.rep_max);
    }
  };

  const allOnTarget = cleared && mine.slice(0, row.sets).every((s) => (s.reps ?? 0) >= row.rep_max);
  const meta = [
    prescriptionLine(row),
    cleared && !doneStyle && last ? `${last.weight_lb} lb` : null,
    cleared && !row.is_path_technique && !doneStyle && allOnTarget ? 'all on target' : null,
  ]
    .filter(Boolean)
    .join(' · ');

  const nextSetNo = editing ? editing.set_no : mine.length + 1;
  const label = editing
    ? `Save set ${editing.set_no}`
    : doneStyle
      ? `Mark done${row.sets > 1 ? ` ${nextSetNo}/${row.sets}` : ''} · +${SET_XP} XP`
      : `Log set ${nextSetNo}${nextSetNo > row.sets ? ' (extra)' : ` · +${SET_XP} XP`}`;

  function log() {
    if (x3 && band) {
      const prefs = useTrainingPrefs.getState();
      prefs.set({ lastBand: { ...prefs.lastBand, [row.exercise]: band } });
    }
    onLog({
      weight_lb: x3 ? 0 : weight,
      reps: doneStyle ? 1 : reps,
      supersedes: editing ?? undefined,
      exercise: step ?? undefined,
      band: x3 ? (band ?? undefined) : undefined,
    });
    setEditing(null);
  }

  return (
    <View
      style={[
        styles.card,
        { backgroundColor: colors.panel, borderColor: cleared ? colors.good : colors.line, borderWidth: cleared ? 2 : 1 },
      ]}>
      <Pressable
        onPress={onToggle}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        accessibilityLabel={`${row.name}, ${prescriptionLine(row)}, ${done} of ${row.sets} sets${cleared ? ', cleared' : ''}`}
        style={styles.head}>
        <View style={[styles.num, { backgroundColor: cleared ? colors.good : colors.panelRaised }]}>
          <KText variant="bodyStrong" color={cleared ? 'night900' : 'inkMuted'}>
            {cleared ? '✓' : number}
          </KText>
        </View>
        <View style={styles.title}>
          <View style={styles.nameRow}>
            <KText variant="bodyStrong" style={styles.name}>
              {row.name}
              {stepInfo ? <KText variant="bodyStrong" color="kiHot">{` · ${stepInfo.name}`}</KText> : null}
            </KText>
            {row.is_path_technique && (
              <View style={[styles.tag, { borderColor: colors.kiHot }]}>
                <KText variant="label" color="kiHot" style={styles.tagText}>
                  Path
                </KText>
              </View>
            )}
          </View>
          <KText variant="caption" color="inkMuted">
            {meta}
            {row.is_swap && garage ? <KText variant="caption" color="volt">{' · swapped'}</KText> : null}
          </KText>
        </View>
        <KText variant="dataSm" color="inkMuted">
          {done}/{row.sets}
        </KText>
      </Pressable>

      {expanded && (
        <View style={styles.body}>
          <FormCues info={formOf?.(step ?? row.exercise)} open={showForm} onToggle={() => setShowForm((v) => !v)} />
          {row.steps && row.steps.length > 0 && (
            <View style={styles.stepBlock}>
              <KText variant="label" color="inkMuted">
                Progression step
              </KText>
              <View style={styles.chips} accessibilityRole="radiogroup">
                {row.steps.map((s, i) => {
                  const on = s.exercise === step;
                  const current = s.exercise === row.current_step;
                  return (
                    <Pressable
                      key={s.exercise}
                      onPress={() => setStep(s.exercise)}
                      accessibilityRole="radio"
                      accessibilityState={{ checked: on }}
                      accessibilityLabel={`Step ${i + 1}: ${s.name}${current ? ', your current step' : ''}`}
                      style={[
                        styles.stepChip,
                        { borderColor: on ? colors.kiHot : colors.line, backgroundColor: on ? colors.panelRaised : 'transparent' },
                      ]}>
                      <KText variant="caption" color={on ? 'kiHot' : 'ink'}>
                        {i + 1}. {s.name}
                      </KText>
                      {current && (
                        <KText variant="label" color="inkMuted" style={styles.tagText}>
                          You
                        </KText>
                      )}
                    </Pressable>
                  );
                })}
              </View>
              {upNext && (
                <Pressable
                  onPress={() => setStep(upNext.exercise)}
                  accessibilityRole="button"
                  style={[styles.advance, { borderColor: colors.good }]}>
                  <KText variant="caption" color="good">
                    ✓ Every set at the top last time. Ready for {upNext.name}? Tap to switch.
                  </KText>
                </Pressable>
              )}
            </View>
          )}
          <View style={styles.chips}>
            {Array.from({ length: Math.max(row.sets, mine.length) }, (_, i) => {
              const s = mine[i];
              const top = s && (s.reps ?? 0) >= row.rep_max;
              const isEditing = editing && s && editing.client_id === s.client_id;
              return (
                <Pressable
                  key={s?.client_id ?? `empty-${i}`}
                  disabled={!s}
                  onPress={() => s && setEditing(isEditing ? null : s)}
                  accessibilityRole={s ? 'button' : 'text'}
                  accessibilityLabel={
                    s
                      ? `Set ${i + 1}: ${doneStyle ? 'done' : `${s.weight_lb} pounds × ${s.reps}`}${top ? ', top of range' : ''}. Tap to edit`
                      : `Set ${i + 1}, not logged`
                  }
                  style={[
                    styles.chip,
                    s
                      ? { backgroundColor: top ? `${colors.good}33` : colors.panelRaised, borderColor: isEditing ? colors.volt : top ? colors.good : colors.panelRaised }
                      : { borderColor: colors.line, borderStyle: 'dashed' },
                  ]}>
                  <KText variant="dataSm" color={s ? 'ink' : 'inkFaint'}>
                    {s ? setLabel(s, doneStyle) : `Set ${i + 1}`}
                  </KText>
                </Pressable>
              );
            })}
          </View>

          {x3 && (
            <View style={styles.stepBlock}>
              <KText variant="label" color="inkMuted">
                Band
              </KText>
              <View style={styles.chips} accessibilityRole="radiogroup">
                {bands.map((b) => {
                  const on = b === band;
                  return (
                    <Pressable
                      key={b}
                      onPress={() => setBand(b)}
                      accessibilityRole="radio"
                      accessibilityState={{ checked: on }}
                      style={[
                        styles.stepChip,
                        { borderColor: on ? colors.kiHot : colors.line, backgroundColor: on ? colors.panelRaised : 'transparent' },
                      ]}>
                      <KText variant="caption" color={on ? 'kiHot' : 'ink'}>
                        {b}
                      </KText>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          )}
          {!doneStyle && (
            <View style={styles.steppers}>
              {!x3 && <Stepper value={weight} unit="lb" step={increment} min={0} onChange={setWeight} label="Weight" />}
              <Stepper value={reps} unit="reps" step={1} min={0} onChange={setReps} label="Reps" />
            </View>
          )}
          {row.note ? (
            <KText variant="caption" color="inkFaint">
              {row.note}
            </KText>
          ) : null}
          <RestSetting row={row} />
          <LogButton label={label} onPress={log} showXp={!editing && nextSetNo <= row.sets} />
          {editing && (
            <Pressable onPress={() => setEditing(null)} accessibilityRole="button" style={styles.cancel}>
              <KText variant="caption" color="inkMuted">
                Cancel edit
              </KText>
            </Pressable>
          )}
        </View>
      )}
    </View>
  );
}

/** A logged set on its chip: "100×8", "24 · Dark gray" (X3), "✓ 45 s", "✓ done". */
export function setLabel(s: Pick<LocalSet, 'weight_lb' | 'reps' | 'seconds' | 'band'>, doneStyle: boolean): string {
  if (s.band) return `${s.reps ?? 0} · ${s.band}`;
  if (doneStyle) return s.seconds ? `✓ ${s.seconds} s` : '✓ done';
  return `${s.weight_lb}×${s.reps}`;
}

/** "Form" toggle and the cue bubble for the exercise being done. */
export function FormCues({ info, open, onToggle }: { info?: FormInfo; open: boolean; onToggle: () => void }) {
  const { colors } = useTheme();
  if (!info?.cues?.length && !info?.setup) return null;
  return (
    <View>
      <Pressable
        onPress={onToggle}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`Form cues for ${info.name}`}
        style={[styles.formBtn, { borderColor: open ? colors.volt : colors.line }]}>
        <KText variant="caption" color="volt">
          {open ? 'Hide form' : 'ⓘ Form'}
        </KText>
      </Pressable>
      {open && (
        <View style={[styles.bubble, { backgroundColor: colors.night800, borderColor: colors.volt }]}>
          <KText variant="label" color="volt">
            {info.name}
          </KText>
          {info.setup ? (
            <KText variant="caption" color="inkMuted">
              {info.setup}
            </KText>
          ) : null}
          {info.cues?.map((c) => (
            <View key={c} style={styles.cueRow}>
              <KText variant="caption" color="volt">
                •
              </KText>
              <KText variant="caption" style={styles.cueText}>
                {c}
              </KText>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

export function Stepper({
  value,
  unit,
  step,
  min,
  onChange,
  label,
}: {
  value: number;
  unit: string;
  step: number;
  min: number;
  onChange: (v: number) => void;
  label: string;
}) {
  const { colors } = useTheme();
  const round = (v: number) => Math.round(v * 100) / 100;
  return (
    <View style={[styles.stepper, { borderColor: colors.line, backgroundColor: colors.night800 }]} accessibilityLabel={`${label} ${value} ${unit}`}>
      <Pressable
        onPress={() => onChange(Math.max(min, round(value - step)))}
        accessibilityRole="button"
        accessibilityLabel={`Decrease ${label.toLowerCase()} by ${step}`}
        style={[styles.stepBtn, { backgroundColor: colors.panelRaised }]}>
        <KText variant="stat">−</KText>
      </Pressable>
      <View style={styles.stepValue}>
        <KText variant="stat">{value}</KText>
        <KText variant="label" color="inkMuted">
          {unit}
        </KText>
      </View>
      <Pressable
        onPress={() => onChange(round(value + step))}
        accessibilityRole="button"
        accessibilityLabel={`Increase ${label.toLowerCase()} by ${step}`}
        style={[styles.stepBtn, { backgroundColor: colors.panelRaised }]}>
        <KText variant="stat">+</KText>
      </Pressable>
    </View>
  );
}

/** The in-card solid button with the "+5 XP" float on press (off under reduced motion). */
function LogButton({ label, onPress, showXp }: { label: string; onPress: () => void; showXp: boolean }) {
  const { colors } = useTheme();
  const reduceMotion = useReducedMotion();
  const float = useSharedValue(0);
  const style = useAnimatedStyle(() => ({
    opacity: float.value === 0 ? 0 : 1 - float.value * 0.85,
    transform: [{ translateY: -36 * float.value }],
  }));
  return (
    <View>
      {showXp && !reduceMotion && (
        <Animated.View style={[styles.float, style]} pointerEvents="none">
          <KText variant="stat" color="kiHot" style={[styles.floatText, { textShadowColor: colors.ki }]}>
            +{SET_XP} XP
          </KText>
        </Animated.View>
      )}
      <Pressable
        onPress={() => {
          if (showXp && !reduceMotion) float.value = withSequence(withTiming(0.001, { duration: 0 }), withTiming(1, { duration: 700 }), withTiming(0, { duration: 0 }));
          onPress();
        }}
        accessibilityRole="button"
        style={({ pressed }) => [styles.log, { backgroundColor: colors.ink, opacity: pressed ? 0.85 : 1 }]}>
        <KText variant="cardTitle" color="night900">
          {label}
        </KText>
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
  name: { flexShrink: 1 },
  tag: { borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 1 },
  tagText: { fontSize: 9, lineHeight: 12 },
  stepBlock: { gap: spacing[2] },
  formBtn: { alignSelf: 'flex-start', minHeight: 36, paddingHorizontal: spacing[3], borderRadius: radius.pill, borderWidth: 1, justifyContent: 'center' },
  bubble: { marginTop: spacing[2], borderWidth: 1, borderRadius: radius.md, padding: spacing[3], gap: spacing[2] },
  cueRow: { flexDirection: 'row', gap: spacing[2] },
  cueText: { flex: 1 },
  stepChip: { minHeight: 44, paddingHorizontal: spacing[3], borderRadius: radius.md, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  advance: { borderWidth: 1, borderRadius: radius.md, padding: spacing[2], minHeight: 44, justifyContent: 'center' },
  body: { paddingHorizontal: spacing[4], paddingBottom: spacing[4], gap: spacing[3] },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  chip: { minWidth: 76, minHeight: 44, paddingHorizontal: spacing[3], borderRadius: radius.md, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  steppers: { flexDirection: 'row', gap: spacing[3] },
  stepper: { flex: 1, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: radius.lg, padding: spacing[1] },
  stepBtn: { width: 48, height: 52, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  stepValue: { flex: 1, alignItems: 'center' },
  log: { minHeight: 52, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing[3] },
  float: { position: 'absolute', right: spacing[3], top: -8, zIndex: 2 },
  floatText: { textShadowRadius: 12, textShadowOffset: { width: 0, height: 0 } },
  cancel: { alignSelf: 'center', minHeight: 44, justifyContent: 'center', paddingHorizontal: spacing[3] },
});
