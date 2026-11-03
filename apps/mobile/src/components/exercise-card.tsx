import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withSequence, withTiming } from 'react-native-reanimated';

import { KText } from '@/components/k-text';
import type { LocalSet } from '@/db/repo';
import { isDoneStyle, prescriptionLine, setsForRow, type Row } from '@/lib/train';
import { SET_XP } from '@/lib/xp';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

export type LogInput = { weight_lb: number; reps: number; supersedes?: LocalSet };

type Props = {
  row: Row;
  number: number;
  sets: LocalSet[]; // current (latest) sets of this session
  expanded: boolean;
  increment: number;
  garage: boolean;
  onToggle: () => void;
  onLog: (input: LogInput) => void;
};

/** One exercise: tap the header to expand; chips, weight and rep steppers, and the Log set button. */
export function ExerciseCard({ row, number, sets, expanded, increment, garage, onToggle, onLog }: Props) {
  const { colors } = useTheme();
  const mine = setsForRow(row, sets);
  const done = Math.min(mine.length, row.sets);
  const cleared = done >= row.sets;
  const doneStyle = isDoneStyle(row);
  const last = mine[mine.length - 1];

  const [weight, setWeight] = useState(last?.weight_lb ?? row.prefill_weight_lb ?? 0);
  const [reps, setReps] = useState(last?.reps ?? row.rep_max);
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
    onLog({ weight_lb: weight, reps: doneStyle ? 1 : reps, supersedes: editing ?? undefined });
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
                    {s ? (doneStyle ? '✓ done' : `${s.weight_lb}×${s.reps}`) : `Set ${i + 1}`}
                  </KText>
                </Pressable>
              );
            })}
          </View>

          {!doneStyle && (
            <View style={styles.steppers}>
              <Stepper value={weight} unit="lb" step={increment} min={0} onChange={setWeight} label="Weight" />
              <Stepper value={reps} unit="reps" step={1} min={0} onChange={setReps} label="Reps" />
            </View>
          )}
          {row.note ? (
            <KText variant="caption" color="inkFaint">
              {row.note}
            </KText>
          ) : null}
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

function Stepper({
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
