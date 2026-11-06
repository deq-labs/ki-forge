import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { Platform, Pressable, ScrollView, Share, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Circle } from 'react-native-svg';

import { KText } from '@/components/k-text';
import { Silhouette } from '@/components/silhouette';
import { GhostButton, Panel } from '@/components/ui';
import { getDb } from '@/db/db';
import { deleteOwner } from '@/db/repo';
import { api, ApiError } from '@/lib/api';
import { defaultApiUrl } from '@/lib/config';
import { parseIsoDate, shortDate } from '@/lib/dates';
import { useMe, useProgram, useTrials } from '@/lib/queries';
import { levelProgress } from '@/lib/xp';
import { useSettings } from '@/state/settings';
import { useTrainingPrefs } from '@/state/training-prefs';
import { toast } from '@/state/toast';
import { textStyle, useTheme } from '@/theme/theme';
import { pathColors, radius, spacing, type PathSlug } from '@/theme/tokens';

/** Profile and account (docs/06-screens.md §7). The subscription card arrives with M6. */
export default function ProfileScreen() {
  const { colors } = useTheme();
  const me = useMe();

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]} edges={['top']}>
      <ScrollView contentContainerStyle={styles.body}>
        {me.data ? (
          <>
            <Header />
            <PathCard />
            <TrialResults />
            <Settings />
            <TrainingSettings />
            <RunActions />
            <DevSection />
          </>
        ) : (
          <KText color="inkMuted">{me.error ? `Can't reach the server: ${me.error.message}` : 'Loading…'}</KText>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Header() {
  const { colors } = useTheme();
  const me = useMe().data!;
  const p = levelProgress(me.stats.total_xp);
  const r = 34;
  const circ = 2 * Math.PI * r;
  return (
    <View style={styles.header}>
      <View style={styles.avatar} accessibilityLabel={`Level ${p.level}`}>
        <Svg width={80} height={80}>
          <Circle cx={40} cy={40} r={r} stroke={colors.panelRaised} strokeWidth={5} fill={colors.panel} />
          <Circle
            cx={40}
            cy={40}
            r={r}
            stroke={colors.ki}
            strokeWidth={5}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${circ * p.fraction} ${circ}`}
            transform="rotate(-90 40 40)"
          />
        </Svg>
        <KText variant="screenTitle" style={styles.avatarLevel}>
          {p.level}
        </KText>
      </View>
      <View style={styles.flex}>
        <KText variant="screenTitle" numberOfLines={1}>
          {me.user.display_name}
        </KText>
        <KText color="inkMuted">
          {me.stats.rank} · {me.stats.total_xp.toLocaleString()} XP
          {me.stats.power_level != null ? ` · Power Level ${me.stats.power_level}` : ''}
        </KText>
      </View>
    </View>
  );
}

function PathCard() {
  const { colors } = useTheme();
  const router = useRouter();
  const me = useMe().data!;
  const program = useProgram();
  const path = program.data?.paths.find((p) => p.slug === me.enrollment?.path_slug);
  const pc = pathColors[(me.enrollment?.path_slug as PathSlug) ?? 'storm'] ?? pathColors.storm;
  return (
    <Pressable
      onPress={() => router.push('/paths')}
      accessibilityRole="button"
      accessibilityLabel={`Path: ${path?.name ?? ''}. Change path`}
      style={[styles.pathCard, { backgroundColor: colors.panel, borderColor: colors.ki }]}>
      <Silhouette ratio={path?.ratio_target ?? 1.5} color={pc.kiHot} size={44} />
      <View style={styles.flex}>
        <KText variant="label" color="inkMuted">
          Path
        </KText>
        <KText variant="cardTitle">{path?.name ?? '—'}</KText>
      </View>
      <KText variant="bodyStrong" color="volt">
        Change
      </KText>
    </Pressable>
  );
}

/** Every Trial with its numbers; tap to enter or edit (lifts, reps, row, bodyweight, shoulders, waist). */
function TrialResults() {
  const { colors } = useTheme();
  const router = useRouter();
  const trials = useTrials();
  if (!trials.data) return null;
  return (
    <Panel style={styles.list}>
      <KText variant="cardTitle" style={styles.listTitle}>
        Trial results
      </KText>
      {trials.data.map((t, i) => {
        const entered = Object.values(t.results).filter((v) => v !== null).length;
        return (
          <Pressable
            key={t.phase_ord}
            onPress={() => router.push({ pathname: '/trial/[ord]', params: { ord: String(t.phase_ord) } })}
            accessibilityRole="button"
            accessibilityLabel={`${t.name}, ${entered} of 9 entered${t.complete ? ', complete' : ''}. Edit results`}
            style={[styles.row, i > 0 && { borderTopColor: colors.line, borderTopWidth: 1 }]}>
            <View style={styles.flex}>
              <KText variant="bodyStrong">
                {t.complete ? '✓ ' : ''}
                {t.name}
              </KText>
              <KText variant="caption" color="inkMuted">
                {shortDate(parseIsoDate(t.start_date))} · {entered}/9 tests
                {t.power_level != null ? ` · Power Level ${t.power_level}` : ''}
                {t.frame_ratio != null ? ` · ratio ${t.frame_ratio.toFixed(2)}` : ''}
              </KText>
            </View>
            <KText variant="bodyStrong" color={entered ? 'volt' : 'inkMuted'}>
              {entered ? 'Edit' : 'Enter'} ›
            </KText>
          </Pressable>
        );
      })}
    </Panel>
  );
}

function Checkbox({ checked }: { checked: boolean }) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.check,
        { borderColor: checked ? colors.volt : colors.inkFaint, backgroundColor: checked ? colors.volt : 'transparent' },
      ]}>
      {checked && (
        <KText variant="bodyStrong" color="night900">
          ✓
        </KText>
      )}
    </View>
  );
}

function SettingRow({
  label,
  hint,
  value,
  onPress,
  role = 'button',
  checked,
  first,
}: {
  label: string;
  hint?: string;
  value?: ReactNode;
  onPress: () => void;
  role?: 'button' | 'checkbox';
  checked?: boolean;
  first?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole={role}
      accessibilityState={role === 'checkbox' ? { checked: !!checked } : undefined}
      accessibilityHint={hint}
      style={({ pressed }) => [styles.row, !first && { borderTopColor: colors.line, borderTopWidth: 1 }, pressed && { opacity: 0.7 }]}>
      <View style={styles.flex}>
        <KText>{label}</KText>
        {hint ? (
          <KText variant="caption" color="inkMuted">
            {hint}
          </KText>
        ) : null}
      </View>
      {role === 'checkbox' ? <Checkbox checked={!!checked} /> : value}
    </Pressable>
  );
}

function Settings() {
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail);
  const me = useMe().data!;
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<unknown>, done?: string) {
    setBusy(true);
    try {
      await fn();
      await queryClient.invalidateQueries({ queryKey: ['me', owner] });
      if (done) toast(done);
    } catch (e) {
      toast(e instanceof ApiError && e.offline ? 'Needs a connection to the server.' : String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function exportData() {
    const data = await api.get('/v1/export');
    const json = JSON.stringify(data, null, 2);
    if (Platform.OS === 'web') {
      const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `ki-forge-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      await Share.share({ message: json, title: 'Ki Forge export' });
    }
  }

  const garageDefault = me.enrollment?.garage_mode_default ?? false;
  return (
    <Panel style={[styles.list, busy && { opacity: 0.7 }]}>
      <SettingRow
        first
        label="Units"
        value={
          <KText variant="dataSm" color="inkMuted">
            {me.user.units === 'metric' ? 'kg · cm' : 'lb · in'}
          </KText>
        }
        hint="Tap to switch"
        onPress={() => void run(() => api.patch('/v1/me', { units: me.user.units === 'metric' ? 'imperial' : 'metric' }))}
      />
      {me.enrollment && (
        <SettingRow
          label="Garage mode by default"
          hint="Start sessions with rack, rower and treadmill moves swapped"
          role="checkbox"
          checked={garageDefault}
          onPress={() =>
            void run(() =>
              api.raw('patch', `/v1/enrollments/${me.enrollment!.id}`, { body: { garage_mode_default: !garageDefault } }),
            )
          }
        />
      )}
      <SettingRow
        label="Keep progress photos"
        hint={me.user.keep_photos ? 'On: photos are kept' : 'Off: photos are deleted after each scan'}
        role="checkbox"
        checked={me.user.keep_photos}
        onPress={() => void run(() => api.patch('/v1/me', { keep_photos: !me.user.keep_photos }))}
      />
      <SettingRow
        label="Export my data"
        value={<KText color="inkMuted">›</KText>}
        onPress={() => void run(exportData, Platform.OS === 'web' ? 'Export downloaded' : undefined)}
      />
    </Panel>
  );
}

function Segmented<T extends number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.segBlock}>
      <KText>{label}</KText>
      <View style={styles.seg} accessibilityRole="radiogroup" accessibilityLabel={label}>
        {options.map((o) => {
          const on = o.value === value;
          return (
            <Pressable
              key={o.value}
              onPress={() => onChange(o.value)}
              accessibilityRole="radio"
              accessibilityState={{ checked: on }}
              style={[styles.segItem, { borderColor: on ? colors.volt : colors.line, backgroundColor: on ? colors.panelRaised : 'transparent' }]}>
              <KText variant="caption" color={on ? 'volt' : 'ink'}>
                {o.label}
              </KText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** Rest timer settings, kept on this device. Per-exercise rest is set from each exercise card in Train. */
function TrainingSettings() {
  const { colors } = useTheme();
  const prefs = useTrainingPrefs();
  const customCount = Object.keys(prefs.perExercise).length;
  return (
    <Panel style={styles.list}>
      <KText variant="cardTitle" style={styles.listTitle}>
        Training
      </KText>
      <SettingRow
        first
        label="Rest timer"
        hint="Starts after each set; keeps counting with the screen off"
        role="checkbox"
        checked={prefs.restEnabled}
        onPress={() => prefs.set({ restEnabled: !prefs.restEnabled })}
      />
      <View style={[styles.segWrap, { borderTopColor: colors.line }]}>
        <Segmented
          label="Rest length"
          value={prefs.restAdjust}
          onChange={(v) => prefs.set({ restAdjust: v })}
          options={[
            { value: -30, label: '−30 s' },
            { value: -15, label: '−15 s' },
            { value: 0, label: 'Program' },
            { value: 15, label: '+15 s' },
            { value: 30, label: '+30 s' },
          ]}
        />
        <Segmented
          label="Between superset exercises"
          value={prefs.supersetTransition}
          onChange={(v) => prefs.set({ supersetTransition: v })}
          options={[
            { value: 0, label: 'No rest' },
            { value: 15, label: '15 s' },
            { value: 30, label: '30 s' },
          ]}
        />
      </View>
      <SettingRow
        label="Custom rest per exercise"
        hint={customCount ? `${customCount} exercise${customCount === 1 ? '' : 's'} set from Train · tap to reset` : 'Set it from an exercise card in Train'}
        value={customCount ? <KText color="volt">Reset</KText> : undefined}
        onPress={() => customCount && prefs.set({ perExercise: {} })}
      />
    </Panel>
  );
}


/** Restart the program (new path and start date) and delete the account, each with a confirmation step. */
function RunActions() {
  const { colors } = useTheme();
  const queryClient = useQueryClient();
  const { devEmail, signOut } = useSettings();
  const me = useMe().data!;
  const [confirm, setConfirm] = useState<'restart' | 'delete' | null>(null);
  const [busy, setBusy] = useState(false);

  async function restart() {
    if (!me.enrollment) return;
    setBusy(true);
    try {
      await api.raw('post', `/v1/enrollments/${me.enrollment.id}/end`, { body: { status: 'abandoned' } });
      await queryClient.invalidateQueries({ queryKey: ['me', devEmail] });
      await queryClient.invalidateQueries({ queryKey: ['week', devEmail] });
      // With no active run the app routes to onboarding: path, then start date.
    } catch (e) {
      toast(e instanceof ApiError && e.offline ? 'Restarting needs a connection to the server.' : String((e as Error).message));
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  }

  async function deleteAccount() {
    setBusy(true);
    try {
      await api.raw('delete', '/v1/me');
      if (devEmail) await deleteOwner(await getDb(), devEmail).catch(() => {});
      queryClient.clear();
      signOut();
    } catch (e) {
      toast(e instanceof ApiError && e.offline ? 'Deleting needs a connection to the server.' : String((e as Error).message));
      setBusy(false);
      setConfirm(null);
    }
  }

  return (
    <View style={styles.actions}>
      {confirm === 'restart' ? (
        <Panel style={[styles.confirm, { borderColor: colors.volt }]}>
          <KText variant="cardTitle">Restart the program?</KText>
          <KText color="inkMuted">
            You&apos;ll pick a path and a start date again, beginning with Trial 0. Your XP, level, badges and past
            sessions stay; the current run is kept in your history.
          </KText>
          <View style={styles.confirmRow}>
            <View style={styles.flex}>
              <GhostButton label="Cancel" onPress={() => setConfirm(null)} />
            </View>
            <View style={styles.flex}>
              <Pressable
                onPress={() => void restart()}
                disabled={busy}
                accessibilityRole="button"
                style={[styles.confirmBtn, { backgroundColor: colors.volt, opacity: busy ? 0.5 : 1 }]}>
                <KText variant="bodyStrong" color="night900">
                  {busy ? 'Restarting…' : 'Restart'}
                </KText>
              </Pressable>
            </View>
          </View>
        </Panel>
      ) : (
        me.enrollment && <GhostButton label="Restart the program" onPress={() => setConfirm('restart')} />
      )}

      {confirm === 'delete' ? (
        <Panel style={[styles.confirm, { borderColor: colors.danger }]}>
          <KText variant="cardTitle" color="danger">
            Delete your account and all data?
          </KText>
          <KText color="inkMuted">
            This removes your logs, Trials, scans and photos within 24 hours and can&apos;t be undone. Export your data
            first if you want a copy.
          </KText>
          <View style={styles.confirmRow}>
            <View style={styles.flex}>
              <GhostButton label="Keep my account" onPress={() => setConfirm(null)} />
            </View>
            <View style={styles.flex}>
              <Pressable
                onPress={() => void deleteAccount()}
                disabled={busy}
                accessibilityRole="button"
                style={[styles.confirmBtn, { backgroundColor: colors.danger, opacity: busy ? 0.5 : 1 }]}>
                <KText variant="bodyStrong" color="night900">
                  {busy ? 'Deleting…' : 'Delete everything'}
                </KText>
              </Pressable>
            </View>
          </View>
        </Panel>
      ) : (
        <>
          <Pressable
            onPress={() => setConfirm('delete')}
            accessibilityRole="button"
            style={[styles.danger, { borderColor: colors.danger }]}>
            <KText variant="bodyStrong" color="danger">
              Delete account and all data
            </KText>
          </Pressable>
          <KText variant="caption" color="inkMuted" style={styles.center}>
            Deletes your logs, scans and photos within 24 hours.
          </KText>
        </>
      )}
    </View>
  );
}

/** Dev identity and server address (until real sign-in in M6). */
function DevSection() {
  const { colors } = useTheme();
  const queryClient = useQueryClient();
  const { devEmail, apiUrlOverride, signOut, setApiUrl } = useSettings();
  const [url, setUrl] = useState(apiUrlOverride ?? '');
  return (
    <Panel style={styles.dev}>
      <KText variant="label" color="inkFaint">
        Signed in as
      </KText>
      <KText variant="bodyStrong">{devEmail}</KText>
      <KText variant="label" color="inkFaint" style={styles.devGap}>
        Server
      </KText>
      <TextInput
        value={url}
        onChangeText={setUrl}
        placeholder={defaultApiUrl()}
        placeholderTextColor={colors.inkFaint}
        autoCapitalize="none"
        autoCorrect={false}
        inputMode="url"
        accessibilityLabel="Server address"
        onEndEditing={() => {
          setApiUrl(url || null);
          void queryClient.invalidateQueries();
        }}
        style={[textStyle('dataSm'), styles.input, { color: colors.ink, backgroundColor: colors.night800, borderColor: colors.line }]}
      />
      <View style={styles.devGap}>
        <GhostButton
          label="Switch user"
          onPress={() => {
            queryClient.clear();
            signOut();
          }}
        />
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  flex: { flex: 1 },
  center: { textAlign: 'center' },
  body: { padding: spacing[4], gap: spacing[4], paddingBottom: spacing[6] },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing[4] },
  avatar: { width: 80, height: 80, alignItems: 'center', justifyContent: 'center' },
  avatarLevel: { position: 'absolute' },
  pathCard: { flexDirection: 'row', alignItems: 'center', gap: spacing[3], borderWidth: 1.5, borderRadius: radius.lg, padding: spacing[4], minHeight: 72 },
  list: { padding: 0, overflow: 'hidden' },
  listTitle: { paddingHorizontal: spacing[4], paddingTop: spacing[4], paddingBottom: spacing[2] },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing[3], paddingHorizontal: spacing[4], minHeight: 60, paddingVertical: spacing[3] },
  check: { width: 28, height: 28, borderRadius: 6, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  actions: { gap: spacing[3] },
  confirm: { gap: spacing[3], borderWidth: 1.5 },
  confirmRow: { flexDirection: 'row', gap: spacing[3] },
  confirmBtn: { minHeight: 48, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center' },
  danger: { minHeight: 52, borderWidth: 1.5, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center' },
  dev: { gap: spacing[1] },
  segWrap: { borderTopWidth: 1, padding: spacing[4], gap: spacing[4] },
  segBlock: { gap: spacing[2] },
  seg: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  segItem: { minHeight: 44, minWidth: 56, paddingHorizontal: spacing[3], borderRadius: radius.md, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  devGap: { marginTop: spacing[3] },
  input: { minHeight: 48, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing[3] },
});
