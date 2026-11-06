import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { KText } from '@/components/k-text';
import { baseRest, type Row } from '@/lib/train';
import { useTrainingPrefs } from '@/state/training-prefs';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

export function mmss(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** "Rest 1:30 · Change" on an exercise card; your own rest for this exercise, kept on this device. */
export function RestSetting({ row }: { row: Row }) {
  const { colors } = useTheme();
  const prefs = useTrainingPrefs();
  const [open, setOpen] = useState(false);
  const rest = baseRest(row, prefs);
  const custom = prefs.perExercise[row.exercise] != null;
  const set = (v: number) => prefs.setExerciseRest(row.exercise, Math.max(15, Math.min(600, v)));

  if (!open) {
    return (
      <Pressable onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel={`Rest ${mmss(rest)}. Change`} style={styles.line}>
        <KText variant="caption" color="inkMuted">
          Rest {mmss(rest)}
          {custom ? ' (yours)' : ''} ·{' '}
        </KText>
        <KText variant="caption" color="volt">
          Change
        </KText>
      </Pressable>
    );
  }
  return (
    <View style={[styles.box, { borderColor: colors.line }]}>
      <KText variant="caption" color="inkMuted" style={styles.flex}>
        Rest for {row.name}
      </KText>
      <Pressable onPress={() => set(rest - 15)} accessibilityRole="button" accessibilityLabel="15 seconds less" style={[styles.btn, { backgroundColor: colors.panelRaised }]}>
        <KText variant="bodyStrong">−15</KText>
      </Pressable>
      <KText variant="dataSm" style={styles.value}>
        {mmss(rest)}
      </KText>
      <Pressable onPress={() => set(rest + 15)} accessibilityRole="button" accessibilityLabel="15 seconds more" style={[styles.btn, { backgroundColor: colors.panelRaised }]}>
        <KText variant="bodyStrong">+15</KText>
      </Pressable>
      {custom && (
        <Pressable onPress={() => prefs.setExerciseRest(row.exercise, null)} accessibilityRole="button" style={styles.btn}>
          <KText variant="caption" color="volt">
            Reset
          </KText>
        </Pressable>
      )}
      <Pressable onPress={() => setOpen(false)} accessibilityRole="button" style={styles.btn}>
        <KText variant="caption" color="inkMuted">
          Done
        </KText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  line: { flexDirection: 'row', alignItems: 'center', minHeight: 44 },
  box: { flexDirection: 'row', alignItems: 'center', gap: spacing[2], borderWidth: 1, borderRadius: radius.md, padding: spacing[2], flexWrap: 'wrap' },
  btn: { minHeight: 44, minWidth: 44, paddingHorizontal: spacing[2], borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  value: { minWidth: 44, textAlign: 'center' },
});
