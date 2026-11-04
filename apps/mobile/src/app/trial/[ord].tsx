import type { components } from '@kiforge/api-types';
import { useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { GhostButton, Panel, PrimaryButton } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { shortDate, parseIsoDate } from '@/lib/dates';
import { useTrials } from '@/lib/queries';
import { useSync } from '@/lib/sync';
import { ALL_TESTS, formatField, GROUPS, parseField, TRIAL_DAYS } from '@/lib/trial-form';
import { useSettings } from '@/state/settings';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

type TrialOut = components['schemas']['TrialOut'];
type TrialSaved = components['schemas']['TrialSaved'];

/** Trial entry: the 9 tests, saved as you go. Power Level, frame ratio and completion come from the server. */
export default function TrialScreen() {
  const { colors } = useTheme();
  const { ord, day } = useLocalSearchParams<{ ord: string; day?: string }>();
  const trials = useTrials();
  const trial = trials.data?.find((t) => String(t.phase_ord) === ord);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      {trials.isPending ? (
        <ActivityIndicator color={colors.ki} style={styles.loading} />
      ) : !trial ? (
        <View style={styles.pad}>
          <Panel>
            <KText color="danger" accessibilityRole="alert">
              {trials.error ? `Can't load your Trials: ${trials.error.message}` : 'No such Trial.'}
            </KText>
          </Panel>
        </View>
      ) : (
        // Keyed so the form starts from the server's values once they arrive.
        <TrialForm key={trial.phase_ord} trial={trial} day={day} />
      )}
    </SafeAreaView>
  );
}

function TrialForm({ trial, day }: { trial: TrialOut; day?: string }) {
  const { colors } = useTheme();
  const router = useRouter();
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail);
  const [text, setText] = useState<Record<string, string>>(() =>
    Object.fromEntries(ALL_TESTS.map((t) => [t, formatField(t, trial.results[t])])),
  );
  const [server, setServer] = useState({
    power_level: trial.power_level,
    frame_ratio: trial.frame_ratio,
    complete: trial.complete,
  });
  const [saving, setSaving] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const invalid = ALL_TESTS.filter((t) => parseField(t, text[t] ?? '') === undefined);
  const entered = ALL_TESTS.filter((t) => {
    const v = parseField(t, text[t] ?? '');
    return v !== null && v !== undefined;
  }).length;

  async function save(type: string, value: number | null) {
    setSaving((n) => n + 1);
    setError(null);
    try {
      const res = (await api.raw('put', `/v1/trials/${trial.phase_ord}`, {
        body: { results: { [type]: value } },
      })) as TrialSaved;
      setServer({ power_level: res.power_level, frame_ratio: res.frame_ratio, complete: res.complete });
      if (res.xp_awarded.length || res.level_up || res.new_badges.length) {
        useSync.setState({ lastReward: { ...res, sessions: [], accepted: { sessions: [], sets: [] } } as never });
      }
      void queryClient.invalidateQueries({ queryKey: ['me', owner] });
      void queryClient.invalidateQueries({ queryKey: ['trials', owner] });
    } catch (e) {
      setError(
        e instanceof ApiError && e.offline
          ? 'Saving Trial results needs a connection to the server. Your entries stay on this screen.'
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setSaving((n) => n - 1);
    }
  }

  function onChange(type: string, value: string) {
    setText((t) => ({ ...t, [type]: value }));
    const parsed = parseField(type, value);
    clearTimeout(timers.current[type]);
    if (parsed === undefined) return; // not a valid entry yet: don't save
    timers.current[type] = setTimeout(() => void save(type, parsed), 700);
  }

  const plan = TRIAL_DAYS.find((d) => d.key === day);
  // With ?day=, show only that day's tests (Train links here from its Trial-week day tabs).
  const groups = plan
    ? GROUPS.map((g) => ({ ...g, fields: g.fields.filter((f) => plan.tests.includes(f.type)) })).filter((g) => g.fields.length)
    : GROUPS;
  const start = parseIsoDate(trial.start_date);
  const toGo = 9 - entered;

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <KText variant="label" color="inkMuted">
          Week of {shortDate(start)}
        </KText>
        <KText variant="screenTitle" accessibilityRole="header">
          {trial.name}
        </KText>

        <Panel style={styles.readout}>
          <View>
            <KText variant="label" color="inkMuted">
              Power Level
            </KText>
            <KText variant="statXl" color="kiHot">
              {server.power_level ?? '—'}
            </KText>
          </View>
          <View style={styles.right}>
            <KText variant="label" color="inkMuted">
              Frame ratio
            </KText>
            <KText variant="stat">{server.frame_ratio != null ? server.frame_ratio.toFixed(2) : '—'}</KText>
            <KText variant="caption" color={server.complete ? 'good' : 'inkMuted'}>
              {server.complete ? '✓ Trial complete' : `${entered} of 9 entered`}
              {saving ? ' · saving…' : ''}
            </KText>
          </View>
        </Panel>

        {plan && (
          <Panel style={[styles.group, { borderColor: colors.volt }]}>
            <KText variant="label" color="volt">
              {plan.day}
            </KText>
            <KText>{plan.what}</KText>
            {!plan.tests.length && (
              <KText variant="caption" color="inkMuted">
                Nothing to enter today.
              </KText>
            )}
          </Panel>
        )}
        {groups.map((g) => (
          <Panel key={g.title} style={styles.group}>
            <KText variant="cardTitle">{g.title}</KText>
            {g.fields.map((f) => {
              const bad = invalid.includes(f.type);
              return (
                <View key={f.type} style={styles.field}>
                  <KText style={styles.flex}>{f.label}</KText>
                  <TextInput
                    value={text[f.type]}
                    onChangeText={(v) => onChange(f.type, v)}
                    placeholder={f.placeholder}
                    placeholderTextColor={colors.inkFaint}
                    inputMode={f.type === 'row_2k_seconds' ? 'text' : 'decimal'}
                    keyboardType={f.type === 'row_2k_seconds' ? 'numbers-and-punctuation' : 'decimal-pad'}
                    accessibilityLabel={`${f.label} in ${f.unit}`}
                    style={[
                      textStyle('stat'),
                      styles.input,
                      { color: colors.ink, backgroundColor: colors.night800, borderColor: bad ? colors.danger : colors.line },
                    ]}
                  />
                  <KText variant="caption" color="inkMuted" style={styles.unit}>
                    {f.unit}
                  </KText>
                </View>
              );
            })}
          </Panel>
        ))}
        {invalid.length > 0 && (
          <KText variant="caption" color="danger">
            Check the highlighted fields (numbers only; the row as minutes:seconds, e.g. 8:30).
          </KText>
        )}
        {error && (
          <KText color="danger" accessibilityRole="alert">
            {error}
          </KText>
        )}

        {!plan && (
          <Panel style={styles.group}>
            <KText variant="cardTitle">Test week schedule</KText>
            {TRIAL_DAYS.map((d) => (
              <View key={d.key} style={styles.schedule}>
                <KText variant="bodyStrong" style={styles.day}>
                  {d.day}
                </KText>
                <KText variant="caption" color="inkMuted" style={styles.flex}>
                  {d.what}
                </KText>
              </View>
            ))}
          </Panel>
        )}

        <PrimaryButton
          label={server.complete ? 'Trial complete · Done' : `Complete Trial · +500 XP · ${toGo} to go`}
          disabled={!server.complete}
          onPress={() => router.back()}
        />
        {!server.complete && <GhostButton label="Save and close" onPress={() => router.back()} />}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  flex: { flex: 1 },
  loading: { marginTop: spacing[6] },
  pad: { padding: spacing[4] },
  body: { padding: spacing[4], gap: spacing[3], paddingBottom: spacing[6] },
  readout: { flexDirection: 'row', justifyContent: 'space-between' },
  right: { alignItems: 'flex-end' },
  group: { gap: spacing[3] },
  field: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
  input: { width: 110, minHeight: 48, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing[3], textAlign: 'right' },
  unit: { width: 40 },
  schedule: { flexDirection: 'row', gap: spacing[3] },
  day: { width: 40 },
});
