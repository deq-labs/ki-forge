import { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withTiming } from 'react-native-reanimated';
import Svg, { Circle } from 'react-native-svg';

import { CarIcon } from '@/components/icons';
import { KText } from '@/components/k-text';
import { useMe, useProgram } from '@/lib/queries';
import { levelProgress } from '@/lib/xp';
import { useSettings } from '@/state/settings';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** Garage mode for today: the device toggle, else the run's default. */
export function useGarage(): [boolean, (on: boolean) => void] {
  const me = useMe();
  const override = useSettings((s) => s.garage);
  const setGarage = useSettings((s) => s.setGarage);
  return [override ?? me.data?.enrollment?.garage_mode_default ?? false, setGarage];
}

const RING = 56;
const STROKE = 5;

/**
 * Level ring, rank · path, XP bar and garage toggle, pinned at the top of every tab screen.
 * The ring and bar show progress within the current level; the right side says what is left.
 */
export function Hud() {
  const { colors } = useTheme();
  const me = useMe();
  const program = useProgram();
  const [garage, setGarage] = useGarage();
  const reduceMotion = useReducedMotion();

  const xp = me.data?.stats.total_xp ?? 0;
  const p = levelProgress(xp);
  const pathName = program.data?.paths.find((x) => x.slug === me.data?.enrollment?.path_slug)?.name ?? '';
  const rank = me.data?.stats.rank ?? '';

  const fill = useSharedValue(p.fraction);
  useEffect(() => {
    fill.value = reduceMotion
      ? p.fraction
      : withTiming(p.fraction, { duration: 600, easing: Easing.out(Easing.back(1.4)) });
  }, [p.fraction, reduceMotion, fill]);
  const barStyle = useAnimatedStyle(() => ({ width: `${Math.max(0, Math.min(1, fill.value)) * 100}%` }));

  const r = (RING - STROKE) / 2;
  const circ = 2 * Math.PI * r;

  return (
    <View style={styles.row} accessibilityRole="summary">
      <View style={styles.ring} accessibilityLabel={`Level ${p.level}`}>
        <Svg width={RING} height={RING}>
          <Circle cx={RING / 2} cy={RING / 2} r={r} stroke={colors.panelRaised} strokeWidth={STROKE} fill="none" />
          <Circle
            cx={RING / 2}
            cy={RING / 2}
            r={r}
            stroke={colors.ki}
            strokeWidth={STROKE}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${circ * p.fraction} ${circ}`}
            transform={`rotate(-90 ${RING / 2} ${RING / 2})`}
          />
        </Svg>
        <KText variant="stat" style={styles.level}>
          {p.level}
        </KText>
      </View>

      <View style={styles.middle}>
        <KText variant="cardTitle" numberOfLines={1}>
          {rank}
          {pathName ? ` · ${pathName}` : ''}
        </KText>
        <View
          style={[styles.track, { backgroundColor: colors.panelRaised }]}
          accessibilityLabel={`${p.xpIntoLevel} of ${p.xpIntoLevel + p.xpToNext} XP into level ${p.level}`}>
          <Animated.View style={[styles.bar, { backgroundColor: colors.ki }, barStyle]} />
        </View>
        <View style={styles.numbers}>
          <KText variant="dataSm" color="inkMuted">
            {xp.toLocaleString()} XP
          </KText>
          <KText variant="dataSm" color="inkMuted">
            {p.xpToNext.toLocaleString()} to Lv {p.level + 1}
          </KText>
        </View>
      </View>

      <Pressable
        onPress={() => setGarage(!garage)}
        accessibilityRole="switch"
        accessibilityLabel="Garage mode"
        accessibilityHint="Swaps rack, rower and treadmill moves for garage alternatives"
        accessibilityState={{ checked: garage }}
        style={[
          styles.garage,
          { borderColor: garage ? colors.volt : 'transparent', backgroundColor: garage ? colors.panel : 'transparent' },
        ]}>
        <CarIcon color={garage ? colors.volt : colors.inkMuted} size={30} />
        {garage && (
          <KText variant="label" color="volt" style={styles.garageLabel}>
            On
          </KText>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing[3], paddingVertical: spacing[2] },
  ring: { width: RING, height: RING, alignItems: 'center', justifyContent: 'center' },
  level: { position: 'absolute' },
  middle: { flex: 1, gap: 6 },
  track: { height: 8, borderRadius: 4, overflow: 'hidden' },
  bar: { height: 8, borderRadius: 4 },
  numbers: { flexDirection: 'row', justifyContent: 'space-between' },
  garage: { minWidth: 48, minHeight: 48, borderRadius: radius.md, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  garageLabel: { fontSize: 9, lineHeight: 10, letterSpacing: 1 },
});
