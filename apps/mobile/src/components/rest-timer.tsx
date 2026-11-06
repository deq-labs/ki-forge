import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { KText } from '@/components/k-text';
import { useRest } from '@/state/rest';
import { useToasts } from '@/state/toast';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

const RING = 44;

function mmss(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

/** Floating rest pill above the tab bar: volt ring (live system state, not progress), +30 s, Skip. */
export function RestTimer() {
  const theme = useTheme();
  const { colors } = theme;
  const { endsAt, total, extend, skip, finish } = useRest();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!endsAt) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [endsAt]);

  // `now` may be a moment stale right after a start; clamp so the first frame never shows more than total.
  const left = endsAt ? Math.min(total, Math.max(0, Math.ceil((endsAt - now) / 1000))) : 0;
  useEffect(() => {
    if (endsAt && left === 0) finish();
  }, [endsAt, left, finish]);

  if (!endsAt) return null;
  const r = (RING - 5) / 2;
  const circ = 2 * Math.PI * r;
  const frac = total ? left / total : 0;

  return (
    <View
      style={[styles.pill, { backgroundColor: colors.panelRaised, borderColor: colors.volt, boxShadow: theme.style.glow ? `0 0 16px ${colors.volt}55` : undefined }]}
      accessibilityRole="timer"
      accessibilityLabel={`Rest ${mmss(left)} left`}
      accessibilityLiveRegion="polite">
      <Svg width={RING} height={RING}>
        <Circle cx={RING / 2} cy={RING / 2} r={r} stroke={colors.line} strokeWidth={5} fill="none" />
        <Circle
          cx={RING / 2}
          cy={RING / 2}
          r={r}
          stroke={colors.volt}
          strokeWidth={5}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${circ * frac} ${circ}`}
          transform={`rotate(-90 ${RING / 2} ${RING / 2})`}
        />
      </Svg>
      <View style={styles.time}>
        <KText variant="label" color="inkMuted">
          Rest
        </KText>
        <KText variant="stat">{mmss(left)}</KText>
      </View>
      <Pressable onPress={() => extend(30)} accessibilityRole="button" accessibilityLabel="Add 30 seconds" style={[styles.btn, { backgroundColor: colors.night800 }]}>
        <KText variant="bodyStrong">+30 s</KText>
      </Pressable>
      <Pressable onPress={skip} accessibilityRole="button" accessibilityLabel="Skip rest" style={[styles.btn, { backgroundColor: colors.night800 }]}>
        <KText variant="bodyStrong">Skip</KText>
      </Pressable>
    </View>
  );
}

/** Toasts stacked above the tab bar. */
export function Toasts() {
  const { colors } = useTheme();
  const toasts = useToasts((s) => s.toasts);
  if (!toasts.length) return null;
  return (
    <View style={styles.toasts} pointerEvents="none">
      {toasts.map((t) => (
        <View key={t.id} style={[styles.toast, { backgroundColor: colors.panelRaised, borderColor: colors.line }]} accessibilityLiveRegion="polite">
          <KText variant="bodyStrong">{t.text}</KText>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    position: 'absolute',
    left: spacing[4],
    right: spacing[4],
    bottom: spacing[3],
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
    padding: spacing[2],
    paddingHorizontal: spacing[3],
    borderRadius: radius.pill,
    borderWidth: 1.5,
  },
  time: { flex: 1 },
  btn: { minHeight: 44, minWidth: 64, paddingHorizontal: spacing[3], borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  toasts: { position: 'absolute', left: spacing[4], right: spacing[4], bottom: 84, gap: spacing[2] },
  toast: { borderWidth: 1, borderRadius: radius.lg, padding: spacing[3], alignItems: 'center' },
});
