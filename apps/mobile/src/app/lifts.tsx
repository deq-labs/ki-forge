import { useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { GhostButton, Panel, PrimaryButton } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { fromLb, liftInput, parseLift } from '@/lib/lifts';
import { useLifts, useMe } from '@/lib/queries';
import { useSettings } from '@/state/settings';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/**
 * 1RMs for % of 1RM targets (Iron Tempo). Opened after enrolling on the path (`from=onboarding`), from
 * Profile › Lifts, and after a deload week (`from=retest`). Saving a lift counts as re-testing it.
 */
export default function Lifts() {
  const lifts = useLifts();
  const me = useMe();
  const { colors } = useTheme();
  if (!lifts.data || !me.data) {
    return (
      <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
        <ActivityIndicator color={colors.ki} style={styles.loading} />
      </SafeAreaView>
    );
  }
  return <LiftsForm lifts={lifts.data.lifts} units={me.data.user.units === 'metric' ? 'metric' : 'imperial'} />;
}

type Lift = { exercise: string; name: string; one_rm_lb: number | null; updated_at: string | null };

function LiftsForm({ lifts, units }: { lifts: Lift[]; units: 'imperial' | 'metric' }) {
  const { colors } = useTheme();
  const router = useRouter();
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail);
  const { from } = useLocalSearchParams<{ from?: string }>();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      lifts.map((l) => [l.exercise, l.one_rm_lb == null ? '' : liftInput(fromLb(l.one_rm_lb, units))]),
    ),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsed = Object.fromEntries(lifts.map((l) => [l.exercise, parseLift(values[l.exercise] ?? '', units)]));
  const invalid = lifts.filter((l) => parsed[l.exercise] === 'invalid');
  const unit = units === 'metric' ? 'kg' : 'lb';

  function done() {
    if (from === 'onboarding') router.replace('/');
    else router.back();
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      // Only changed lifts are sent, so an unchanged one keeps its last-tested date.
      const changed: Record<string, number | null> = {};
      for (const l of lifts) {
        const v = parsed[l.exercise];
        if (v === 'invalid') continue;
        if (v !== l.one_rm_lb && !(v == null && l.one_rm_lb == null)) changed[l.exercise] = v;
      }
      if (from === 'retest') {
        // Re-testing confirms every entered lift, even unchanged ones.
        for (const l of lifts)
          if (parsed[l.exercise] != null && parsed[l.exercise] !== 'invalid')
            changed[l.exercise] ??= parsed[l.exercise] as number;
      }
      if (Object.keys(changed).length) await api.raw('put', '/v1/me/lifts', { body: { lifts: changed } });
      await queryClient.invalidateQueries({ queryKey: ['lifts', owner] });
      await queryClient.invalidateQueries({ queryKey: ['week', owner] });
      done();
    } catch (e) {
      setError(
        e instanceof ApiError && e.offline ? 'Saving your lifts needs a connection.' : String((e as Error).message),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <KText variant="screenTitle" accessibilityRole="header">
          {from === 'retest' ? 'Re-test your lifts' : 'Your 1-rep maxes'}
        </KText>
        <KText color="inkMuted">
          {from === 'retest'
            ? 'A new block starts. Enter what you can lift once with good form now; the EMOM loads follow it.'
            : 'The heaviest weight you can lift once with good form. EMOM loads are a percent of these, e.g. 3 @ 80%. Leave one empty if you are not sure; you can add it later in Profile.'}
        </KText>
        <Panel style={styles.list}>
          {lifts.map((l, i) => {
            const bad = parsed[l.exercise] === 'invalid';
            return (
              <View key={l.exercise} style={[styles.row, i > 0 && { borderTopColor: colors.line, borderTopWidth: 1 }]}>
                <View style={styles.flex}>
                  <KText>{l.name}</KText>
                  {l.updated_at ? (
                    <KText variant="caption" color="inkMuted">
                      Tested {new Date(l.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </KText>
                  ) : null}
                </View>
                <TextInput
                  value={values[l.exercise]}
                  onChangeText={(v) => setValues((s) => ({ ...s, [l.exercise]: v }))}
                  placeholder="—"
                  placeholderTextColor={colors.inkFaint}
                  inputMode="decimal"
                  keyboardType="decimal-pad"
                  accessibilityLabel={`${l.name} one-rep max in ${units === 'metric' ? 'kilograms' : 'pounds'}`}
                  style={[
                    textStyle('dataSm'),
                    styles.input,
                    {
                      color: colors.ink,
                      backgroundColor: colors.night800,
                      borderColor: bad ? colors.danger : colors.line,
                    },
                  ]}
                />
                <KText variant="caption" color="inkMuted" style={styles.unit}>
                  {unit}
                </KText>
              </View>
            );
          })}
        </Panel>
        {invalid.length > 0 && (
          <KText variant="caption" color="danger" accessibilityRole="alert">
            {invalid.map((l) => l.name).join(', ')}: enter a weight above 0, or leave it empty.
          </KText>
        )}
        {error && (
          <KText color="danger" accessibilityRole="alert">
            {error}
          </KText>
        )}
      </ScrollView>
      <View style={styles.footer}>
        <PrimaryButton
          label={saving ? 'Saving…' : 'Save lifts'}
          onPress={save}
          disabled={saving || invalid.length > 0}
        />
        {from === 'onboarding' && <GhostButton label="Skip for now" onPress={done} />}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  loading: { marginTop: spacing[6] },
  body: { padding: spacing[4], gap: spacing[3] },
  list: { paddingVertical: 0 },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing[2], minHeight: 56, paddingVertical: spacing[2] },
  flex: { flex: 1 },
  input: {
    width: 96,
    minHeight: 44,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing[2],
    textAlign: 'right',
  },
  unit: { width: 20 },
  footer: { padding: spacing[4], gap: spacing[2] },
});
