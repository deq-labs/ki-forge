import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Hud } from '@/components/hud';
import { KText } from '@/components/k-text';
import { Panel, PrimaryButton } from '@/components/ui';
import type { Arc, Program } from '@/lib/api';
import { parseIsoDate, shortDate } from '@/lib/dates';
import { useArc, useMe, useProgram, useTrials } from '@/lib/queries';
import { fieldOf, formatField, GROUPS } from '@/lib/trial-form';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

type ArcPhase = Arc['phases'][number];
type ProgramPhase = Program['phases'][number];

/** One line describing a phase, from its program data (RIR, main lift scheme, calories, deloads, extras). */
function describe(p: ProgramPhase): string {
  if (p.kind === 'trial') return 'Test week · 9 tests';
  const m = p.modifiers;
  if (m.deload) return `${m.deload.percent}% loads, fewer EMOM rounds, no finishers or X3`;
  const bits: string[] = [];
  if (m.main_lift_scheme) bits.push(`main lift ${m.main_lift_scheme.sets} × ${m.main_lift_scheme.rep_min}–${m.main_lift_scheme.rep_max}`);
  if (m.main_lift_rir) bits.push(`main lift RIR ${m.main_lift_rir.join('–')}`);
  else if (p.rir_target != null) bits.push(`RIR ${p.rir_target}`);
  if (Object.keys(m.extra_sets).length) bits.push('+2 sets on raises, shrugs and curls');
  if (m.optional_day) bits.push('optional 5th day');
  if (m.extra_conditioning_sessions) bits.push(`+${m.extra_conditioning_sessions} conditioning session`);
  if (m.progression === 'hold_weights') bits.push('hold your weights');
  if (p.deload_every && !m.deload) bits.push(`deload every ${p.deload_every}th week`);
  bits.push(p.calorie_mode === 'surplus' ? 'small surplus' : p.calorie_mode === 'deficit' ? 'calorie deficit' : 'eat at maintenance');
  return bits.join(' · ');
}

function weeksLabel(p: ArcPhase): string {
  return p.start_week === p.end_week ? `Week ${p.start_week}` : `Weeks ${p.start_week}–${p.end_week}`;
}

export default function ArcScreen() {
  const { colors } = useTheme();
  const arc = useArc();
  const program = useProgram();
  const trials = useTrials();
  const [open, setOpen] = useState<ArcPhase | null>(null);

  const phases = arc.data?.phases ?? [];
  // A path with its own block program (Iron Tempo) shows the current block, not the 84-week arc.
  const block = arc.data?.block ?? null;
  const me = useMe();
  const own = program.data?.programs?.find(
    (b) => b.slug === program.data?.paths.find((p) => p.slug === me.data?.enrollment?.path_slug)?.program,
  );
  const byOrd = new Map((own?.phases ?? program.data?.phases ?? []).map((p) => [p.ord, p]));
  const complete = new Map(trials.data?.map((t) => [t.phase_ord, t.complete]) ?? []);
  // Phases are numbered 1, 2, 3… in order; Trials are not counted.
  const phaseNo = new Map(phases.filter((p) => p.kind !== 'trial').map((p, i) => [p.ord, i + 1]));

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]} edges={['top']}>
      <View style={styles.hud}>
        <Hud />
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <KText variant="label" color="inkMuted">
          {block ? `${own?.cycle_weeks ?? 5}-week block · block ${block}` : `${program.data?.cycle_weeks ?? 84}-week arc · cycle 1`}
        </KText>
        <KText variant="screenTitle" accessibilityRole="header">
          {block ? 'Your training block' : 'Your training arc'}
        </KText>
        <KText color="inkMuted">
          {block
            ? 'Four build weeks, then a deload. After the deload a new block starts: re-test your 1-rep maxes.'
            : 'Clear each Trial to unlock the next phase and +500 XP.'}
        </KText>

        {arc.isPending && <ActivityIndicator color={colors.ki} style={styles.loading} />}
        <View style={styles.map}>
          {phases.map((p, i) => {
            const info = byOrd.get(p.ord);
            const isTrial = p.kind === 'trial';
            const done = isTrial ? !!complete.get(p.ord) || p.status === 'past' : p.status === 'past';
            const railAbove = i > 0 && (phases[i - 1].status === 'past' || p.status !== 'future');
            const railBelow = i < phases.length - 1 && p.status === 'past';
            const specialization = !!info?.display_name_template;
            return (
              <View key={p.ord} style={styles.row}>
                <View style={styles.railCol}>
                  <View style={[styles.rail, { backgroundColor: i === 0 ? 'transparent' : railAbove ? colors.ki : colors.panelRaised }]} />
                  <Node
                    label={isTrial ? (done ? '✓' : 'T') : String(phaseNo.get(p.ord))}
                    trial={isTrial}
                    status={p.status}
                    done={done}
                    hot={specialization && p.status !== 'past'}
                    onPress={() => setOpen(p)}
                    a11y={`${p.name}, ${p.status}${done ? ', cleared' : ''}`}
                  />
                  <View
                    style={[
                      styles.rail,
                      { backgroundColor: i === phases.length - 1 ? 'transparent' : railBelow ? colors.ki : colors.panelRaised },
                    ]}
                  />
                </View>
                <Pressable onPress={() => setOpen(p)} style={styles.text} accessibilityRole="button" accessibilityLabel={`${p.name} details`}>
                  {p.status === 'current' && !isTrial ? (
                    <CurrentCard phase={p} arc={arc.data!} info={info} />
                  ) : (
                    <View style={styles.plain}>
                      <KText variant="cardTitle" color={specialization ? 'kiHot' : p.status === 'future' ? 'ink' : 'inkMuted'}>
                        {p.name}
                        {isTrial && done ? ' · cleared' : ''}
                      </KText>
                      <KText variant="dataSm" color="inkMuted">
                        {weeksLabel(p)} · {info ? describe(info) : ''}
                      </KText>
                    </View>
                  )}
                </Pressable>
              </View>
            );
          })}
        </View>
      </ScrollView>
      {open && <PhaseSheet phase={open} info={byOrd.get(open.ord)} onClose={() => setOpen(null)} />}
    </SafeAreaView>
  );
}

function Node({
  label,
  trial,
  status,
  done,
  hot,
  onPress,
  a11y,
}: {
  label: string;
  trial: boolean;
  status: ArcPhase['status'];
  done: boolean;
  hot: boolean;
  onPress: () => void;
  a11y: string;
}) {
  const { colors } = useTheme();
  const reduceMotion = useReducedMotion();
  const pulse = useSharedValue(0);
  useEffect(() => {
    if (status === 'current' && !reduceMotion) {
      pulse.value = withRepeat(withTiming(1, { duration: 1400, easing: Easing.inOut(Easing.sin) }), -1, true);
    }
  }, [status, reduceMotion, pulse]);
  const ring = useAnimatedStyle(() => ({ opacity: 0.25 + 0.5 * pulse.value, transform: [{ scale: 1 + 0.18 * pulse.value }] }));

  const shape = trial ? styles.diamond : styles.orb;
  const border = status === 'current' ? colors.volt : hot ? colors.ki : colors.line;
  const inner = (
    <KText variant="bodyStrong" color={done ? 'onKi' : hot ? 'kiHot' : 'ink'} style={trial ? styles.unrotate : undefined}>
      {label}
    </KText>
  );
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={a11y} style={styles.nodeWrap}>
      {status === 'current' && <Animated.View style={[shape, styles.halo, { borderColor: colors.volt }, ring]} />}
      {done ? (
        <LinearGradient colors={[colors.kiHot, colors.ki]} style={[shape, styles.center]}>
          {inner}
        </LinearGradient>
      ) : (
        <View style={[shape, styles.center, { backgroundColor: colors.panel, borderColor: border, borderWidth: status === 'current' ? 3 : 2 }]}>
          {inner}
        </View>
      )}
    </Pressable>
  );
}

function CurrentCard({ phase, arc, info }: { phase: ArcPhase; arc: Arc; info?: ProgramPhase }) {
  const { colors } = useTheme();
  const progress = arc.progress;
  const next = arc.phases.find((p) => p.ord > phase.ord && p.kind === 'trial');
  const weekIn = progress?.week_in_phase ?? 1;
  const of = progress?.weeks_in_phase ?? phase.end_week - phase.start_week + 1;
  const toTrial = next ? next.start_week - (arc.current_week ?? phase.start_week) : null;
  return (
    <View style={[styles.current, { backgroundColor: colors.panel, borderColor: colors.volt }]}>
      <View style={styles.currentHead}>
        <KText variant="cardTitle">{phase.name}</KText>
        <KText variant="dataSm" color="inkMuted">
          {weeksLabel(phase)}
        </KText>
      </View>
      <KText color="inkMuted">{info ? describe(info) : ''}</KText>
      <View style={[styles.track, { backgroundColor: colors.panelRaised }]}>
        <View style={[styles.fill, { width: `${(100 * weekIn) / of}%`, backgroundColor: colors.volt }]} />
      </View>
      <KText variant="dataSm" color="inkMuted">
        Week {weekIn} of {of}
        {next && toTrial != null && toTrial > 0 ? ` · ${toTrial} week${toTrial === 1 ? '' : 's'} to ${next.name}` : ''}
      </KText>
    </View>
  );
}

/** Bottom sheet: a phase's rules, or a Trial's tests with a way into Trial entry. */
function PhaseSheet({ phase, info, onClose }: { phase: ArcPhase; info?: ProgramPhase; onClose: () => void }) {
  const { colors } = useTheme();
  const router = useRouter();
  const trials = useTrials();
  const reduceMotion = useReducedMotion();
  const trial = trials.data?.find((t) => t.phase_ord === phase.ord);
  const entered = trial ? Object.values(trial.results).filter((v) => v != null).length : 0;
  return (
    <Modal visible transparent animationType={reduceMotion ? 'none' : 'slide'} onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose} accessibilityLabel="Close">
        <Pressable onPress={() => {}} style={[styles.sheet, { backgroundColor: colors.night800, borderColor: colors.line }]}>
          <KText variant="label" color="inkMuted">
            {weeksLabel(phase)} · {shortDate(parseIsoDate(phase.start_date))} – {shortDate(parseIsoDate(phase.end_date))}
          </KText>
          <KText variant="screenTitle">{phase.name}</KText>
          {phase.kind === 'trial' ? (
            <>
              <Panel style={styles.sheetPanel}>
                {GROUPS.flatMap((g) => g.fields).map((f) => {
                  const v = trial?.results[f.type];
                  return (
                    <View key={f.type} style={styles.sheetRow}>
                      <KText style={styles.flex}>{fieldOf(f.type)?.label}</KText>
                      <KText variant="dataSm" color={v != null ? 'ink' : 'inkFaint'}>
                        {v != null ? `${formatField(f.type, v)} ${f.unit === 'mm:ss' ? '' : f.unit}` : '—'}
                      </KText>
                    </View>
                  );
                })}
              </Panel>
              <KText variant="caption" color={trial?.complete ? 'good' : 'inkMuted'}>
                {trial?.complete
                  ? `✓ Complete · Power Level ${trial.power_level}${trial.frame_ratio != null ? ` · frame ${trial.frame_ratio.toFixed(2)}` : ''}`
                  : `${entered} of 9 entered`}
              </KText>
              <PrimaryButton
                label={entered ? 'Edit results' : 'Enter results'}
                onPress={() => {
                  onClose();
                  router.push({ pathname: '/trial/[ord]', params: { ord: String(phase.ord) } });
                }}
              />
            </>
          ) : (
            <Panel style={styles.sheetPanel}>
              <KText>{info ? describe(info) : ''}</KText>
              {info?.modifiers.next ? (
                <KText variant="caption" color="inkMuted">
                  {info.modifiers.next}
                </KText>
              ) : null}
            </Panel>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const NODE = 52;

const styles = StyleSheet.create({
  safe: { flex: 1 },
  flex: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center' },
  hud: { paddingHorizontal: spacing[4] },
  body: { padding: spacing[4], paddingTop: spacing[2], gap: spacing[2], paddingBottom: spacing[6] },
  loading: { marginTop: spacing[6] },
  map: { marginTop: spacing[3] },
  row: { flexDirection: 'row', gap: spacing[3], minHeight: 84 },
  railCol: { width: NODE + 8, alignItems: 'center' },
  rail: { width: 3, flex: 1, minHeight: 8 },
  nodeWrap: { width: NODE + 8, height: NODE + 8, alignItems: 'center', justifyContent: 'center' },
  orb: { width: NODE, height: NODE, borderRadius: NODE / 2 },
  diamond: { width: NODE - 10, height: NODE - 10, borderRadius: 10, transform: [{ rotate: '45deg' }] },
  halo: { position: 'absolute', borderWidth: 3 },
  unrotate: { transform: [{ rotate: '-45deg' }] },
  text: { flex: 1, justifyContent: 'center', paddingVertical: spacing[2] },
  plain: { gap: 2 },
  current: { borderWidth: 1.5, borderRadius: radius.lg, padding: spacing[4], gap: spacing[2] },
  currentHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  track: { height: 8, borderRadius: 4, overflow: 'hidden', marginTop: spacing[1] },
  fill: { height: 8, borderRadius: 4 },
  scrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: { borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, borderWidth: 1, padding: spacing[4], gap: spacing[3], paddingBottom: spacing[6] },
  sheetPanel: { gap: spacing[2] },
  sheetRow: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
});
