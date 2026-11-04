import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useMemo } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Aura } from '@/components/aura';
import { Hud } from '@/components/hud';
import { KText } from '@/components/k-text';
import { Silhouette } from '@/components/silhouette';
import { GhostButton, Panel, PrimaryButton } from '@/components/ui';
import type { Week } from '@/lib/api';
import { addDays, dayName, isoDate, parseIsoDate } from '@/lib/dates';
import { useArc, useMe, useProgram, useTrials, useWeek } from '@/lib/queries';
import { useSync } from '@/lib/sync';
import { maxSessionXp } from '@/lib/xp';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

type WeekSession = Week['sessions'][number];

export default function BaseScreen() {
  const { colors } = useTheme();
  const me = useMe();
  const week = useWeek();
  const arc = useArc();
  const program = useProgram();
  const sync = useSync();

  const refreshing = me.isRefetching || week.isRefetching;
  const refresh = () => {
    void me.refetch();
    void week.refetch();
    void arc.refetch();
  };

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]} edges={['top']}>
      <View style={styles.hud}>
        <Hud />
      </View>
      <ScrollView
        contentContainerStyle={styles.body}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.ki} />}>
        {me.isPending ? (
          <ActivityIndicator color={colors.ki} style={styles.loading} />
        ) : me.error ? (
          <Panel>
            <KText color="danger" accessibilityRole="alert">
              Can&apos;t reach the server. {me.error.message}
            </KText>
          </Panel>
        ) : (
          <>
            <Hero />
            <OpenTrial />
            <NextQuest week={week.data} />
            <ThisWeek week={week.data} />
            <StatTiles
              cleared={me.data.stats.sessions_cleared}
              phaseWeek={
                arc.data?.progress ? `${arc.data.progress.week_in_phase}/${arc.data.progress.weeks_in_phase}` : '—'
              }
              badges={`${me.data.badges.length}/${program.data?.badges.length ?? 6}`}
            />
            <Badges />
            {sync.status !== 'idle' || sync.pending > 0 ? (
              <KText variant="caption" color={sync.status === 'error' ? 'danger' : 'inkFaint'} style={styles.syncLine}>
                {sync.status === 'offline'
                  ? `Offline · ${sync.pending} waiting to sync`
                  : sync.status === 'syncing'
                    ? 'Syncing…'
                    : sync.status === 'error'
                      ? `Sync failed: ${sync.lastError}`
                      : `${sync.pending} waiting to sync`}
              </KText>
            ) : null}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Hero() {
  const { colors } = useTheme();
  const me = useMe();
  const program = useProgram();
  const stats = me.data?.stats;
  const path = program.data?.paths.find((p) => p.slug === me.data?.enrollment?.path_slug);
  const target = path?.ratio_target ?? 1.5;
  const auraColors = useMemo<[string, string]>(() => [colors.ki, colors.kiHot], [colors.ki, colors.kiHot]);
  const router = useRouter();
  const trials = useTrials();
  // Tap the numbers to edit the Trial they came from: the latest one with results, else Trial 0.
  const latest = [...(trials.data ?? [])].reverse().find((t) => Object.values(t.results).some((v) => v != null));
  const editOrd = latest?.phase_ord ?? 0;

  return (
    <Panel style={styles.hero}>
      <LinearGradient
        colors={['transparent', `${colors.ki}33`]}
        start={{ x: 0.5, y: 0.2 }}
        end={{ x: 0.5, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <Aura colors={auraColors} />
      <Pressable
        onPress={() => router.push({ pathname: '/trial/[ord]', params: { ord: String(editOrd) } })}
        accessibilityRole="button"
        accessibilityHint="Opens your Trial results to enter or edit them"
        style={styles.heroTop}>
        <View>
          <KText variant="label" color="inkMuted">
            Power Level
          </KText>
          {stats?.power_level != null ? (
            <KText
              variant="burst"
              color="kiHot"
              style={[styles.power, { textShadowColor: colors.ki }]}
              accessibilityLabel={`Power Level ${stats.power_level}`}>
              {stats.power_level}
            </KText>
          ) : (
            <KText color="inkMuted" style={styles.emptyPower}>
              Run Trial 0 to set your Power Level
            </KText>
          )}
        </View>
        <View style={styles.ratio}>
          <KText variant="label" color="inkMuted">
            Frame ratio
          </KText>
          <KText variant="stat">{stats?.frame_ratio != null ? stats.frame_ratio.toFixed(2) : '—'}</KText>
          <KText variant="caption" color="inkMuted">
            target {target.toFixed(2)}
          </KText>
          <KText variant="caption" color="volt">
            Edit ›
          </KText>
        </View>
      </Pressable>
      <View style={styles.figure}>
        <Silhouette
          ratio={stats?.frame_ratio ?? 1.3}
          color={colors.night800}
          size={150}
          label={`Your frame${stats?.frame_ratio ? ` ${stats.frame_ratio.toFixed(2)}` : ''}, target ${target.toFixed(2)}`}
        />
      </View>
    </Panel>
  );
}

/** A Trial that has started but is not complete (e.g. Trial 0 with tests missing): a way back into it. */
function OpenTrial() {
  const { colors } = useTheme();
  const router = useRouter();
  const trials = useTrials();
  const today = isoDate(new Date());
  const open = trials.data?.find((t) => t.start_date <= today && !t.complete);
  if (!open) return null;
  const entered = Object.values(open.results).filter((v) => v !== null).length;
  return (
    <Panel style={[styles.quest, { borderColor: colors.volt }]}>
      <View style={styles.questText}>
        <KText variant="label" color="volt">
          Trial open
        </KText>
        <KText variant="cardTitle">{open.name}</KText>
        <KText variant="caption" color="inkMuted">
          {entered} of 9 tests entered · finish it for +500 XP
        </KText>
      </View>
      <GhostButton
        label="Enter"
        onPress={() => router.push({ pathname: '/trial/[ord]', params: { ord: String(open.phase_ord) } })}
      />
    </Panel>
  );
}

function sigil(short: string): string {
  const last = short.trim().split(/\s+/).pop() ?? short;
  return last.length === 1 ? last : short.charAt(0);
}

function minutes(s: WeekSession): number {
  const secs = s.prescriptions.reduce((t, p) => t + p.sets * ((p.rest_seconds ?? 60) + 40), 0);
  return Math.max(5, Math.round(secs / 300) * 5);
}

function NextQuest({ week }: { week?: Week }) {
  const { colors } = useTheme();
  const router = useRouter();
  if (!week) return null;
  const today = isoDate(new Date());

  if (week.phase.kind === 'trial') {
    return (
      <>
        <Panel style={styles.quest}>
          <View style={[styles.sigil, { borderColor: colors.volt }]}>
            <KText variant="screenTitle" color="volt">
              ◆
            </KText>
          </View>
          <View style={styles.questText}>
            <KText variant="label" color="inkMuted">
              {week.week < 0 || week.current_week < 0 ? 'Coming up' : 'This week'}
            </KText>
            <KText variant="cardTitle">{week.phase.name}</KText>
            <KText variant="caption" color="inkMuted">
              Test week: measure and test your lifts, then enter the results.
            </KText>
          </View>
        </Panel>
        <PrimaryButton
          label="Enter Trial results"
          onPress={() => router.push({ pathname: '/trial/[ord]', params: { ord: String(week.phase.ord) } })}
        />
      </>
    );
  }

  const open = week.sessions.filter((s) => !s.cleared);
  const next =
    open.find((s) => s.required_for_full_week && s.date >= today) ?? open.find((s) => s.date >= today) ?? open[0];
  if (!next) {
    return (
      <Panel style={styles.quest}>
        <KText variant="cardTitle">Week cleared. Every quest done.</KText>
      </Panel>
    );
  }
  const isToday = next.date === today;
  return (
    <>
      <Panel style={styles.quest}>
        <View style={[styles.sigil, { borderColor: colors.ki, backgroundColor: `${colors.ki}22` }]}>
          <KText variant="screenTitle" color="kiHot">
            {sigil(next.short)}
          </KText>
        </View>
        <View style={styles.questText}>
          <KText variant="label" color="inkMuted">
            {isToday ? "Today's quest" : `Next quest · ${dayName(parseIsoDate(next.date))}`}
          </KText>
          <KText variant="cardTitle">{next.name}</KText>
          <KText variant="caption" color="inkMuted">
            {next.prescriptions.length} exercises · ~{minutes(next)} min · up to{' '}
            {maxSessionXp(next.sets_needed, next.kind)} XP
          </KText>
        </View>
      </Panel>
      <PrimaryButton
        label="Start quest"
        onPress={() => router.push({ pathname: '/train', params: { code: next.code } })}
      />
    </>
  );
}

function ThisWeek({ week }: { week?: Week }) {
  const { colors } = useTheme();
  if (!week) return null;
  const start = parseIsoDate(week.starts_on);
  const today = isoDate(new Date());
  const days = Array.from({ length: 7 }, (_, i) => addDays(start, i));
  return (
    <Panel style={styles.week}>
      <View style={styles.weekHead}>
        <KText variant="cardTitle">This week</KText>
        <KText variant="caption" color="inkMuted">
          5 quests = +150 XP
        </KText>
      </View>
      <View style={styles.days}>
        {days.map((d) => {
          const iso = isoDate(d);
          const cleared = week.sessions.some((s) => s.date === iso && s.cleared);
          const isToday = iso === today;
          return (
            <View
              key={iso}
              style={styles.day}
              accessibilityLabel={`${dayName(d)}${cleared ? ', cleared' : ''}${isToday ? ', today' : ''}`}>
              {cleared ? (
                <LinearGradient
                  colors={[colors.kiHot, colors.ki]}
                  style={[styles.tile, isToday && { borderColor: colors.volt, borderWidth: 2 }]}>
                  <KText variant="bodyStrong" color="onKi">
                    ✓
                  </KText>
                </LinearGradient>
              ) : (
                <View
                  style={[
                    styles.tile,
                    {
                      backgroundColor: colors.panelRaised,
                      borderColor: isToday ? colors.volt : colors.line,
                      borderWidth: isToday ? 2 : 1,
                    },
                  ]}
                />
              )}
              <KText variant="caption" color={isToday ? 'ink' : 'inkMuted'} style={isToday && styles.bold}>
                {dayName(d)}
              </KText>
            </View>
          );
        })}
      </View>
    </Panel>
  );
}

function StatTiles({ cleared, phaseWeek, badges }: { cleared: number; phaseWeek: string; badges: string }) {
  const tiles = [
    { label: 'Sessions cleared', value: String(cleared) },
    { label: 'Phase week', value: phaseWeek },
    { label: 'Badges', value: badges },
  ];
  return (
    <View style={styles.tiles}>
      {tiles.map((t) => (
        <Panel key={t.label} style={styles.statTile}>
          <KText variant="stat">{t.value}</KText>
          <KText variant="caption" color="inkMuted">
            {t.label}
          </KText>
        </Panel>
      ))}
    </View>
  );
}

function Badges() {
  const { colors } = useTheme();
  const me = useMe();
  const program = useProgram();
  if (!program.data) return null;
  const earned = new Set(me.data?.badges.map((b) => b.slug));
  return (
    <View style={styles.badgeSection}>
      <KText variant="cardTitle">Badges</KText>
      <View style={styles.badgeGrid}>
        {program.data.badges.map((b) => {
          const on = earned.has(b.slug);
          return (
            <View
              key={b.slug}
              style={[
                styles.badge,
                {
                  backgroundColor: colors.panel,
                  borderColor: on ? colors.ki : colors.line,
                  opacity: on ? 1 : 0.45,
                },
              ]}
              accessibilityLabel={`${b.name}, ${on ? 'earned' : `locked: ${b.description}`}`}>
              <View
                style={[
                  styles.emblem,
                  {
                    borderColor: on ? colors.kiHot : colors.inkFaint,
                    backgroundColor: on ? `${colors.ki}33` : 'transparent',
                  },
                ]}>
                <KText variant="bodyStrong" color={on ? 'kiHot' : 'inkFaint'} style={styles.unrotate}>
                  {on ? '✓' : '?'}
                </KText>
              </View>
              <KText variant="caption" style={styles.center} numberOfLines={1}>
                {b.name}
              </KText>
              <KText variant="caption" color="inkMuted" style={[styles.center, styles.small]} numberOfLines={2}>
                {b.description}
              </KText>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  hud: { paddingHorizontal: spacing[4] },
  body: {
    padding: spacing[4],
    paddingTop: spacing[2],
    gap: spacing[4],
    paddingBottom: spacing[6],
  },
  loading: { marginTop: spacing[6] },
  hero: { minHeight: 300, overflow: 'hidden', borderRadius: radius.xl },
  heroTop: { flexDirection: 'row', justifyContent: 'space-between' },
  power: { textShadowRadius: 18, textShadowOffset: { width: 0, height: 0 } },
  emptyPower: { maxWidth: 170, marginTop: spacing[2] },
  ratio: { alignItems: 'flex-end' },
  figure: { alignItems: 'center', marginTop: -spacing[4] },
  quest: { flexDirection: 'row', alignItems: 'center', gap: spacing[4] },
  sigil: {
    width: 64,
    height: 64,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  questText: { flex: 1, gap: 2 },
  week: { gap: spacing[3] },
  weekHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  days: { flexDirection: 'row', gap: spacing[2] },
  day: { flex: 1, alignItems: 'center', gap: spacing[1] },
  tile: {
    alignSelf: 'stretch',
    height: 36,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bold: { fontFamily: 'MPLUS1p_800ExtraBold' },
  tiles: { flexDirection: 'row', gap: spacing[3] },
  statTile: { flex: 1, padding: spacing[3], gap: 2 },
  badgeSection: { gap: spacing[3] },
  badgeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[3] },
  badge: {
    width: '30.5%',
    flexGrow: 1,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: spacing[3],
    alignItems: 'center',
    gap: spacing[1],
  },
  emblem: {
    width: 40,
    height: 40,
    borderRadius: 8,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    transform: [{ rotate: '45deg' }],
  },
  unrotate: { transform: [{ rotate: '-45deg' }] },
  center: { textAlign: 'center' },
  small: { fontSize: 11, lineHeight: 14 },
  syncLine: { textAlign: 'center' },
});
