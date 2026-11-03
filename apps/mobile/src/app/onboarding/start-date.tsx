import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { Panel, PrimaryButton, StepHeader } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { addDays, isoDate, mondayOptions, nextMonday, shortDate } from '@/lib/dates';
import { toLb, useOnboarding } from '@/state/onboarding';
import { useSettings } from '@/state/settings';
import { PathThemeProvider, textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** Onboarding step 3: start date (Mondays only; default next Monday) and optional bodyweight. Creates the run. */
export default function StartDate() {
  const path = useOnboarding((s) => s.path);
  return (
    <PathThemeProvider path={path}>
      <StartDateForm />
    </PathThemeProvider>
  );
}

function StartDateForm() {
  const { colors } = useTheme();
  const router = useRouter();
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail);
  const { units, path } = useOnboarding();
  const today = useMemo(() => new Date(), []);
  const options = useMemo(() => mondayOptions(today, 8), [today]);
  const [start, setStart] = useState(isoDate(nextMonday(today)));
  const [bodyweight, setBodyweight] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bw = Number(bodyweight.replace(',', '.'));
  const bwValid = bodyweight === '' || (Number.isFinite(bw) && bw > 20 && bw < 700);

  async function begin() {
    setSaving(true);
    setError(null);
    try {
      if (units !== 'imperial') await api.patch('/v1/me', { units });
      await api.post('/v1/enrollments', { path_slug: path, start_date: start, garage_mode_default: false });
      if (bodyweight !== '') {
        // Bodyweight is a Trial 0 test; entering it now just pre-fills that Trial.
        await api.raw('put', '/v1/trials/0', { body: { results: { bodyweight_lb: toLb(bw, units) } } });
      }
      await queryClient.invalidateQueries({ queryKey: ['me', owner] });
      router.replace('/');
    } catch (e) {
      setError(
        e instanceof ApiError && e.offline
          ? 'Starting a run needs a connection to the server.'
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setSaving(false);
    }
  }

  const startDate = options.find((o) => isoDate(o) === start) ?? nextMonday(today);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <StepHeader step={3} of={3} />
        <KText variant="screenTitle" accessibilityRole="header">
          When do you start?
        </KText>
        <KText color="inkMuted">
          Week 0 is Trial 0, your test week: you measure and test your lifts so every later Trial has something to
          beat. Foundation training starts the Monday after.
        </KText>

        <KText variant="label" color="inkMuted" style={styles.section}>
          Trial 0 starts on
        </KText>
        <View style={styles.dates} accessibilityRole="radiogroup">
          {options.map((o) => {
            const value = isoDate(o);
            const on = value === start;
            return (
              <Pressable
                key={value}
                onPress={() => setStart(value)}
                accessibilityRole="radio"
                accessibilityState={{ checked: on }}
                accessibilityLabel={shortDate(o)}
                style={[
                  styles.date,
                  { borderColor: on ? colors.ki : colors.line, backgroundColor: on ? colors.panelRaised : colors.panel },
                ]}>
                <KText variant="dataSm" color={on ? 'kiHot' : 'ink'}>
                  {shortDate(o)}
                </KText>
              </Pressable>
            );
          })}
        </View>
        <Panel>
          <KText variant="caption" color="inkMuted">
            Trial 0: {shortDate(startDate)} – {shortDate(addDays(startDate, 6))}. Foundation week 1 begins{' '}
            {shortDate(addDays(startDate, 7))}.
          </KText>
        </Panel>

        <KText variant="label" color="inkMuted" style={styles.section}>
          Bodyweight (optional)
        </KText>
        <View style={styles.bwRow}>
          <TextInput
            value={bodyweight}
            onChangeText={setBodyweight}
            placeholder={units === 'metric' ? '86' : '190'}
            placeholderTextColor={colors.inkFaint}
            inputMode="decimal"
            keyboardType="decimal-pad"
            accessibilityLabel={`Bodyweight in ${units === 'metric' ? 'kilograms' : 'pounds'}`}
            style={[
              textStyle('stat'),
              styles.bwInput,
              { color: colors.ink, backgroundColor: colors.panel, borderColor: bwValid ? colors.line : colors.danger },
            ]}
          />
          <KText variant="bodyStrong" color="inkMuted">
            {units === 'metric' ? 'kg' : 'lb'}
          </KText>
        </View>
        {!bwValid && (
          <KText variant="caption" color="danger">
            Enter a bodyweight between 20 and 700, or leave it empty.
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
          label={saving ? 'Starting your run…' : 'Begin the arc'}
          onPress={begin}
          disabled={saving || !bwValid}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  body: { padding: spacing[4], gap: spacing[3] },
  section: { marginTop: spacing[4] },
  dates: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  date: { minHeight: 48, minWidth: '30%', flexGrow: 1, borderWidth: 2, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing[2] },
  bwRow: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
  bwInput: { width: 140, minHeight: 56, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing[3] },
  footer: { padding: spacing[4] },
});
