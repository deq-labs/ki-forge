import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { PrimaryButton, StepHeader } from '@/components/ui';
import { useOnboarding } from '@/state/onboarding';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

const UNITS = [
  { value: 'imperial', label: 'lb · in' },
  { value: 'metric', label: 'kg · cm' },
] as const;

/** Onboarding step 1: welcome and units. */
export default function Welcome() {
  const { colors } = useTheme();
  const router = useRouter();
  const { units, setUnits } = useOnboarding();

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <ScrollView contentContainerStyle={styles.body}>
        <StepHeader step={1} of={3} />
        <KText variant="screenTitle" accessibilityRole="header" style={styles.title}>
          Your arc starts here
        </KText>
        <KText color="inkMuted">
          84 weeks of strength training in phases, with a Trial between each one. Log your sets, earn XP, level up,
          and watch your frame change.
        </KText>

        <KText variant="label" color="inkMuted" style={styles.section}>
          Units
        </KText>
        <View style={styles.segment} accessibilityRole="radiogroup">
          {UNITS.map((u) => {
            const on = units === u.value;
            return (
              <Pressable
                key={u.value}
                onPress={() => setUnits(u.value)}
                accessibilityRole="radio"
                accessibilityState={{ checked: on }}
                style={[
                  styles.option,
                  { borderColor: on ? colors.ki : colors.line, backgroundColor: on ? colors.panelRaised : colors.panel },
                ]}>
                <KText variant="bodyStrong">{u.label}</KText>
                {on && (
                  <KText variant="caption" color="kiHot">
                    ✓ Selected
                  </KText>
                )}
              </Pressable>
            );
          })}
        </View>
      </ScrollView>
      <View style={styles.footer}>
        <PrimaryButton label="Choose your path" onPress={() => router.push('/paths?from=onboarding')} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  body: { padding: spacing[4], gap: spacing[3] },
  title: { marginTop: spacing[4] },
  section: { marginTop: spacing[5] },
  segment: { flexDirection: 'row', gap: spacing[3] },
  option: { flex: 1, minHeight: 64, borderWidth: 2, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center', gap: 2 },
  footer: { padding: spacing[4] },
});
