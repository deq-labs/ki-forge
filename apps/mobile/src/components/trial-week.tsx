import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { KText } from '@/components/k-text';
import { Panel, PrimaryButton } from '@/components/ui';
import { dayName } from '@/lib/dates';
import { useTrials } from '@/lib/queries';
import { fieldOf, formatField, TRIAL_DAYS } from '@/lib/trial-form';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** Train in a Trial week: day tabs with that day's tests; entering them saves into the Trial. */
export function TrialWeek({ phaseOrd, name }: { phaseOrd: number; name: string }) {
  const { colors } = useTheme();
  const router = useRouter();
  const trials = useTrials();
  const trial = trials.data?.find((t) => t.phase_ord === phaseOrd);
  const today = dayName(new Date()).toLowerCase();
  const [pick, setPick] = useState(TRIAL_DAYS.some((d) => d.key === today) ? today : 'mon');
  const plan = TRIAL_DAYS.find((d) => d.key === pick) ?? TRIAL_DAYS[0];
  const doneFor = (tests: string[]) => tests.length > 0 && tests.every((t) => trial?.results[t] != null);

  return (
    <View style={styles.wrap}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabs} style={styles.tabsWrap}>
        {TRIAL_DAYS.map((d) => {
          const on = d.key === plan.key;
          const done = doneFor(d.tests);
          return (
            <Pressable
              key={d.key}
              onPress={() => setPick(d.key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: on }}
              accessibilityLabel={`${d.day}${done ? ', entered' : ''}`}
              style={[styles.tab, { backgroundColor: on ? colors.ink : colors.panel, borderColor: on ? colors.ink : colors.line }]}>
              <KText variant="bodyStrong" color={on ? 'night900' : 'ink'}>
                {done ? '✓ ' : ''}
                {d.day}
              </KText>
            </Pressable>
          );
        })}
      </ScrollView>

      <View style={styles.body}>
        <KText variant="label" color="inkMuted">
          {plan.day} · test week
        </KText>
        <KText variant="screenTitle" accessibilityRole="header">
          {name}
        </KText>
        <Panel style={styles.panel}>
          <KText>{plan.what}</KText>
          {plan.tests.map((t) => {
            const f = fieldOf(t);
            const v = trial?.results[t];
            return (
              <View key={t} style={styles.row}>
                <KText style={styles.flex}>{f?.label ?? t}</KText>
                <KText variant="dataSm" color={v != null ? 'good' : 'inkFaint'}>
                  {v != null ? `✓ ${formatField(t, v)} ${f?.unit === 'mm:ss' ? '' : f?.unit}` : 'not entered'}
                </KText>
              </View>
            );
          })}
        </Panel>
        {plan.tests.length > 0 && (
          <PrimaryButton
            label={doneFor(plan.tests) ? `Edit ${plan.day} results` : `Enter ${plan.day} results`}
            onPress={() => router.push({ pathname: '/trial/[ord]', params: { ord: String(phaseOrd), day: plan.key } })}
          />
        )}
        {trial && (
          <KText variant="caption" color={trial.complete ? 'good' : 'inkMuted'} style={styles.center}>
            {trial.complete
              ? '✓ Trial complete'
              : `${Object.values(trial.results).filter((x) => x != null).length} of 9 tests entered · all 9 for +500 XP`}
          </KText>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1 },
  flex: { flex: 1 },
  center: { textAlign: 'center' },
  tabsWrap: { flexGrow: 0 },
  tabs: { paddingHorizontal: spacing[4], paddingVertical: spacing[3], gap: spacing[2] },
  tab: { minHeight: 44, minWidth: 56, paddingHorizontal: spacing[4], borderRadius: radius.pill, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  body: { paddingHorizontal: spacing[4], gap: spacing[3] },
  panel: { gap: spacing[3] },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
});
