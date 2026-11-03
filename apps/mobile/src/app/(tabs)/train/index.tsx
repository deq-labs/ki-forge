import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ExerciseCard, type LogInput } from '@/components/exercise-card';
import { useGarage } from '@/components/hud';
import { KText } from '@/components/k-text';
import { GhostButton, Panel, PrimaryButton } from '@/components/ui';
import { getDb } from '@/db/db';
import { completeSession, currentSets, ensureSession, findSession, logSet, type LocalSet } from '@/db/repo';
import { dayName, parseIsoDate } from '@/lib/dates';
import { haptic } from '@/lib/feedback';
import { useMe, useProgram, useWeek } from '@/lib/queries';
import { requestSync, syncNow } from '@/lib/sync';
import { nextOpenRow, progress, restSeconds, rowsFor, setsForRow, type Row } from '@/lib/train';
import { useRest } from '@/state/rest';
import { useSettings } from '@/state/settings';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** Train: log the week's sessions offline. Sets go to SQLite first; the sync queue sends them later. */
export default function TrainScreen() {
  const { colors } = useTheme();
  const params = useLocalSearchParams<{ code?: string }>();
  const week = useWeek();
  // A tab tap picks a session; a new ?code= from Base (Start quest) takes over again.
  const [picked, setPicked] = useState<{ param?: string; code: string } | null>(null);
  const code = picked && picked.param === params.code ? picked.code : params.code;
  const setCode = (c: string) => setPicked({ param: params.code, code: c });

  const sessions = week.data?.sessions ?? [];
  const active = sessions.find((s) => s.code === code) ?? sessions.find((s) => !s.cleared) ?? sessions[0];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]} edges={['top']}>
      {week.isPending ? (
        <ActivityIndicator color={colors.ki} style={styles.loading} />
      ) : week.error ? (
        <View style={styles.pad}>
          <Panel>
            <KText color="danger" accessibilityRole="alert">
              This week isn&apos;t on the phone yet. Connect once to download it. ({week.error.message})
            </KText>
          </Panel>
        </View>
      ) : !active ? (
        <View style={styles.pad}>
          <Panel>
            <KText variant="cardTitle">{week.data.phase.name}</KText>
            <KText color="inkMuted">
              A Trial week has no training sessions: it&apos;s for testing your lifts and measurements.
            </KText>
          </Panel>
        </View>
      ) : (
        <>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabs} style={styles.tabsWrap}>
            {sessions.map((s) => {
              const on = s.code === active.code;
              return (
                <Pressable
                  key={s.code}
                  onPress={() => setCode(s.code)}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: on }}
                  accessibilityLabel={`${s.short}${s.cleared ? ', cleared' : ''}`}
                  style={[styles.tab, { backgroundColor: on ? colors.ink : colors.panel, borderColor: on ? colors.ink : colors.line }]}>
                  <KText variant="bodyStrong" color={on ? 'night900' : 'ink'}>
                    {s.cleared ? '✓ ' : ''}
                    {s.short}
                  </KText>
                </Pressable>
              );
            })}
          </ScrollView>
          <SessionView key={`${week.data.week}:${active.code}`} weekNo={week.data.week} session={active} />
        </>
      )}
    </SafeAreaView>
  );
}

type WeekSession = NonNullable<ReturnType<typeof useWeek>['data']>['sessions'][number];

function SessionView({ weekNo, session }: { weekNo: number; session: WeekSession }) {
  const { colors } = useTheme();
  const router = useRouter();
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail)!;
  const me = useMe();
  const program = useProgram();
  const [garage] = useGarage();
  const startRest = useRest((s) => s.start);

  const exercises = useMemo(() => new Map(program.data?.exercises.map((e) => [e.slug, e]) ?? []), [program.data]);
  const rows: Row[] = useMemo(
    () => rowsFor(session.prescriptions, session.garage_mode, garage, (slug) => exercises.get(slug)?.name),
    [session, garage, exercises],
  );

  const localKey = ['local', owner, weekNo, session.code];
  const local = useQuery({
    queryKey: localKey,
    queryFn: async () => {
      const db = await getDb();
      const s = await findSession(db, owner, weekNo, session.code);
      return { session: s, sets: s ? await currentSets(db, s.client_id) : ([] as LocalSet[]) };
    },
  });
  const sets = local.data?.sets ?? [];
  const prog = progress(rows, sets);
  const logged = Math.max(prog.done, session.sets_logged);
  const allDone = logged >= prog.needed && prog.needed > 0;
  const [open, setOpen] = useState<number | null>(null);
  const expanded = open ?? nextOpenRow(prog.rowsDone, -1);

  const pathName = program.data?.paths.find((p) => p.slug === me.data?.enrollment?.path_slug)?.name ?? '';

  async function onLog(row: Row, input: LogInput) {
    const db = await getDb();
    const s = await ensureSession(db, owner, { template_code: session.code, week: weekNo, garage_mode: garage });
    const mine = setsForRow(row, sets);
    await logSet(
      db,
      owner,
      s.client_id,
      {
        exercise_slug: input.supersedes?.exercise_slug ?? row.exercise,
        set_no: input.supersedes?.set_no ?? mine.length + 1,
        weight_lb: input.weight_lb,
        reps: input.reps,
        rir: null,
        is_swap: input.supersedes?.is_swap ?? row.is_swap,
      },
      input.supersedes?.client_id ?? null,
    );
    haptic.set();
    await queryClient.invalidateQueries({ queryKey: localKey });
    requestSync(queryClient);
    if (!input.supersedes) {
      const doneAfter = mine.length + 1;
      startRest(restSeconds(row, doneAfter));
      if (doneAfter >= row.sets) {
        const after = [...prog.rowsDone];
        after[row.index] = true;
        setOpen(nextOpenRow(after, row.index));
      }
    }
  }

  async function clearQuest() {
    const db = await getDb();
    const s = local.data?.session ?? (await findSession(db, owner, weekNo, session.code));
    if (s) await completeSession(db, s.client_id);
    haptic.cleared();
    useRest.getState().skip();
    void syncNow(queryClient); // the rewards overlay shows the server's result
    router.navigate('/');
  }

  function saveAndExit() {
    requestSync(queryClient, 0);
    router.navigate('/');
  }

  return (
    <ScrollView contentContainerStyle={styles.body}>
      <View style={styles.header}>
        <KText variant="label" color="inkMuted">
          {dayName(parseIsoDate(session.date))}
          {pathName ? ` · ${pathName}` : ''}
        </KText>
        <View style={styles.titleRow}>
          <KText variant="screenTitle" accessibilityRole="header" style={styles.flex}>
            {session.name}
          </KText>
          <KText variant="stat">
            {logged}
            <KText variant="dataSm" color="inkMuted">
              /{prog.needed} sets
            </KText>
          </KText>
        </View>
        <View style={[styles.track, { backgroundColor: colors.panelRaised }]} accessibilityLabel={`${logged} of ${prog.needed} sets logged`}>
          <View style={[styles.fill, { width: `${prog.needed ? (100 * logged) / prog.needed : 0}%`, backgroundColor: colors.ki }]} />
        </View>
      </View>

      {garage && (
        <View style={[styles.banner, { borderColor: colors.volt }]}>
          <KText variant="caption" color="volt">
            Garage mode on. Rack, rower and treadmill moves are swapped.
          </KText>
        </View>
      )}
      {session.cleared && (
        <View style={[styles.banner, { borderColor: colors.good }]}>
          <KText variant="caption" color="good">
            ✓ Quest cleared. Extra sets are saved but earn no XP.
          </KText>
        </View>
      )}

      {rows.map((row, i) => (
        <ExerciseCard
          key={`${row.index}:${row.exercise}`}
          row={row}
          number={i + 1}
          sets={sets}
          expanded={expanded === i}
          increment={exercises.get(row.exercise)?.increment_lb ?? 5}
          garage={garage}
          onToggle={() => setOpen(expanded === i ? -1 : i)}
          onLog={(input) => void onLog(row, input)}
        />
      ))}

      <View style={styles.actions}>
        {allDone && !session.cleared ? (
          <PrimaryButton label="Clear quest" onPress={() => void clearQuest()} />
        ) : session.cleared ? null : (
          <PrimaryButton label={`Clear quest · ${prog.needed - logged} sets to go`} onPress={() => {}} disabled />
        )}
        <GhostButton label="Save and exit" onPress={saveAndExit} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  loading: { marginTop: spacing[6] },
  pad: { padding: spacing[4] },
  tabsWrap: { flexGrow: 0 },
  tabs: { paddingHorizontal: spacing[4], paddingVertical: spacing[3], gap: spacing[2] },
  tab: { minHeight: 44, paddingHorizontal: spacing[4], borderRadius: radius.pill, borderWidth: 1, justifyContent: 'center' },
  body: { padding: spacing[4], paddingTop: 0, gap: spacing[3], paddingBottom: 140 },
  header: { gap: spacing[2] },
  titleRow: { flexDirection: 'row', alignItems: 'baseline', gap: spacing[3] },
  flex: { flex: 1 },
  track: { height: 8, borderRadius: 4, overflow: 'hidden' },
  fill: { height: 8, borderRadius: 4 },
  banner: { borderWidth: 1, borderRadius: radius.md, padding: spacing[3] },
  actions: { gap: spacing[3], marginTop: spacing[2] },
});
