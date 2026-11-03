import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useMemo } from 'react';
import { Modal, StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import { create } from 'zustand';

import { KText } from '@/components/k-text';
import { Panel, PrimaryButton } from '@/components/ui';
import { haptic } from '@/lib/feedback';
import { useProgram } from '@/lib/queries';
import { breakdown, momentOf, nextRankLine, type Breakdown, type Reward } from '@/lib/rewards';
import { useSync } from '@/lib/sync';
import { toast } from '@/state/toast';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** The quest being cleared, so the card can name it ("Quest cleared · Push & Shoulders"). */
export const useQuestName = create<{ name: string | null; set: (n: string | null) => void }>((set) => ({
  name: null,
  set: (name) => set({ name }),
}));

/**
 * Global rewards, mounted once in the root layout. After a sync that raises the level: the full-screen
 * POWER SURGE overlay. A cleared quest without a level up: the same breakdown as a bottom sheet. A badge
 * on its own: a toast. Per-set syncs show nothing here (the +5 XP float already did).
 */
export function Rewards() {
  const reward = useSync((s) => s.lastReward) as Reward | null;
  const clear = useSync((s) => s.clearReward);
  const questName = useQuestName((s) => s.name);
  const moment = reward ? momentOf(reward) : null;

  useEffect(() => {
    if (!reward) return;
    if (moment === 'badge' || moment === null) {
      for (const b of reward.new_badges) toast(`Badge earned: ${b.name} · +${b.xp_reward} XP`);
      clear();
      return;
    }
    if (moment === 'level_up') haptic.levelUp();
  }, [reward, moment, clear]);

  if (!reward || (moment !== 'level_up' && moment !== 'quest')) return null;
  const close = () => {
    useQuestName.getState().set(null);
    clear();
  };
  return moment === 'level_up' ? (
    <LevelUp reward={reward} questName={questName} onClose={close} />
  ) : (
    <QuestSheet reward={reward} questName={questName} onClose={close} />
  );
}

function LevelUp({ reward, questName, onClose }: { reward: Reward; questName: string | null; onClose: () => void }) {
  const { colors } = useTheme();
  const program = useProgram();
  const reduceMotion = useReducedMotion();
  const level = reward.level_up!.to;
  const copy = nextRankLine(level, program.data?.ranks ?? []);
  const b = breakdown(reward);

  const slam = useSharedValue(reduceMotion ? 1 : 0);
  useEffect(() => {
    if (!reduceMotion) slam.value = withDelay(250, withSpring(1, { damping: 9, stiffness: 160 }));
  }, [reduceMotion, slam]);
  const slamStyle = useAnimatedStyle(() => ({
    opacity: Math.min(1, slam.value * 1.5),
    transform: [{ scale: 2.2 - 1.2 * slam.value }],
  }));

  return (
    <Modal visible transparent animationType={reduceMotion ? 'none' : 'fade'} onRequestClose={onClose} statusBarTranslucent>
      <View style={[styles.full, { backgroundColor: colors.night900 }]}>
        <LinearGradient
          colors={[`${colors.ki}00`, `${colors.ki}66`, `${colors.ki}00`]}
          locations={[0, 0.35, 0.75]}
          style={StyleSheet.absoluteFill}
        />
        {!reduceMotion && <Burst colors={[colors.ki, colors.kiHot]} />}
        <SafeAreaView style={styles.fullBody}>
          <View style={styles.center} accessibilityRole="header" accessibilityLabel={`Power surge. Level ${level}, ${reward.level_up!.rank}`}>
            <KText variant="label" color="kiHot">
              Power surge
            </KText>
            <Animated.View style={slamStyle}>
              <KText variant="burst" style={[styles.lv, { textShadowColor: colors.ki }]}>
                LV {level}
              </KText>
            </Animated.View>
            <KText variant="screenTitle" color="kiHot">
              {reward.level_up!.rank}
            </KText>
            {copy && (
              <KText color="inkMuted" style={styles.copy}>
                {copy}
              </KText>
            )}
          </View>
          <BreakdownCard b={b} questName={questName} />
          <BadgeCards reward={reward} />
          <PrimaryButton label="Keep training" onPress={onClose} />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

function QuestSheet({ reward, questName, onClose }: { reward: Reward; questName: string | null; onClose: () => void }) {
  const { colors } = useTheme();
  const reduceMotion = useReducedMotion();
  return (
    <Modal visible transparent animationType={reduceMotion ? 'none' : 'slide'} onRequestClose={onClose}>
      <View style={styles.scrim}>
        <SafeAreaView edges={['bottom']} style={[styles.sheet, { backgroundColor: colors.night800, borderColor: colors.line }]}>
          <BreakdownCard b={breakdown(reward)} questName={questName} />
          <BadgeCards reward={reward} />
          <PrimaryButton label="Keep training" onPress={onClose} />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

function BreakdownCard({ b, questName }: { b: Breakdown; questName: string | null }) {
  const { colors } = useTheme();
  return (
    <Panel style={styles.card}>
      <KText variant="label" color="inkMuted">
        {b.questCleared ? 'Quest cleared' : 'XP earned'}
        {questName ? ` · ${questName}` : ''}
      </KText>
      {b.lines.map((l) => (
        <View key={l.label} style={styles.line}>
          <KText>{l.label}</KText>
          <KText variant="dataSm">+{l.xp}</KText>
        </View>
      ))}
      <View style={[styles.line, styles.totalLine, { borderTopColor: colors.line }]}>
        <KText variant="bodyStrong">Total</KText>
        <KText variant="stat" color="kiHot">
          +{b.total} XP
        </KText>
      </View>
    </Panel>
  );
}

function BadgeCards({ reward }: { reward: Reward }) {
  const { colors } = useTheme();
  return (
    <>
      {reward.new_badges.map((badge) => (
        <Panel key={badge.slug} style={styles.badge}>
          <View style={[styles.emblem, { borderColor: colors.kiHot, backgroundColor: `${colors.ki}33` }]}>
            <KText variant="bodyStrong" color="kiHot" style={styles.unrotate}>
              ✓
            </KText>
          </View>
          <View style={styles.flex}>
            <KText variant="bodyStrong">Badge unlocked: {badge.name}</KText>
            <KText variant="caption" color="inkMuted">
              {badge.description} · +{badge.xp_reward} XP
            </KText>
          </View>
        </Panel>
      ))}
    </>
  );
}

/** Radial burst of particles in the path colors (Reanimated; skipped under reduced motion). */
function Burst({ colors }: { colors: [string, string] }) {
  const dots = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => {
        const angle = (i / 18) * Math.PI * 2 + (i % 2) * 0.17;
        const dist = 110 + ((i * 47) % 90);
        return { dx: Math.cos(angle) * dist, dy: Math.sin(angle) * dist, size: 6 + ((i * 7) % 14), color: colors[i % 3 === 0 ? 1 : 0] };
      }),
    [colors],
  );
  return (
    <View style={styles.burst} pointerEvents="none">
      {dots.map((d, i) => (
        <Particle key={i} {...d} delay={150 + (i % 6) * 40} />
      ))}
    </View>
  );
}

function Particle({ dx, dy, size, color, delay }: { dx: number; dy: number; size: number; color: string; delay: number }) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withDelay(delay, withTiming(1, { duration: 1100, easing: Easing.out(Easing.cubic) }));
  }, [delay, t]);
  const style = useAnimatedStyle(() => ({
    opacity: t.value < 0.8 ? 1 : 1 - (t.value - 0.8) * 3,
    transform: [{ translateX: dx * t.value }, { translateY: dy * t.value }],
  }));
  return <Animated.View style={[{ position: 'absolute', width: size, height: size, borderRadius: size / 2, backgroundColor: color }, style]} />;
}

const styles = StyleSheet.create({
  full: { flex: 1 },
  fullBody: { flex: 1, padding: spacing[4], gap: spacing[4], justifyContent: 'center' },
  center: { alignItems: 'center', gap: spacing[2] },
  lv: { fontSize: 88, lineHeight: 96, textShadowRadius: 24, textShadowOffset: { width: 0, height: 0 } },
  copy: { textAlign: 'center', maxWidth: 300 },
  burst: { position: 'absolute', top: '28%', left: '50%', width: 0, height: 0 },
  scrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: { borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, borderWidth: 1, padding: spacing[4], gap: spacing[3] },
  card: { gap: spacing[2] },
  line: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  totalLine: { borderTopWidth: 1, paddingTop: spacing[2], marginTop: spacing[1] },
  badge: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
  emblem: { width: 40, height: 40, borderRadius: 8, borderWidth: 2, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '45deg' }] },
  unrotate: { transform: [{ rotate: '-45deg' }] },
  flex: { flex: 1 },
});
