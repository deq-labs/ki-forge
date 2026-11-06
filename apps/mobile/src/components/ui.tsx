import { LinearGradient } from 'expo-linear-gradient';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { KText } from '@/components/k-text';
import { energyFill, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** A surface on the night ground: `panel` with a `line` border (raised = `panelRaised`). */
export function Panel({
  children,
  raised,
  style,
}: {
  children: ReactNode;
  raised?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const { colors, style: theme } = useTheme();
  return (
    <View
      style={[
        styles.panel,
        {
          backgroundColor: raised ? colors.panelRaised : colors.panel,
          borderColor: colors.line,
          borderWidth: theme.border,
          borderRadius: theme.radius,
        },
        style,
      ]}>
      {children}
    </View>
  );
}

/**
 * The primary energy button: starts or finishes something that earns XP; one per screen. Ki gradient,
 * `on-ki` text, a pressed depth that drops 4 px. Disabled says why in its label and drops to 38%.
 */
export function PrimaryButton({
  label,
  onPress,
  disabled,
  accessibilityHint,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  accessibilityHint?: string;
}) {
  const t = useTheme();
  const { colors } = t;
  const r = { borderRadius: t.style.radius };
  // Flat themes: a hard offset shadow (ink on light themes) instead of a shaded gradient.
  const depth = t.style.scheme === 'light' ? colors.ink : shade(colors.ki);
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!disabled }}
      style={[styles.primaryWrap, { opacity: disabled ? 0.38 : 1 }]}>
      {({ pressed }) => (
        <View style={[styles.primaryDepth, r, { backgroundColor: depth, paddingBottom: pressed ? 2 : 6 }]}>
          <LinearGradient
            colors={energyFill(t)}
            start={{ x: 0, y: 0 }}
            end={{ x: 0, y: 1 }}
            style={[styles.primary, r, { marginTop: pressed ? 4 : 0 }]}>
            <KText variant="cardTitle" color="onKi" style={styles.primaryText}>
              {label}
            </KText>
          </LinearGradient>
        </View>
      )}
    </Pressable>
  );
}

/** Dismissals and secondary paths. */
export function GhostButton({ label, onPress }: { label: string; onPress: () => void }) {
  const { colors, style: theme } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.ghost,
        { borderColor: colors.line, borderWidth: theme.border, borderRadius: theme.radius, opacity: pressed ? 0.7 : 1 },
      ]}>
      <KText variant="bodyStrong">{label}</KText>
    </Pressable>
  );
}

/** "STEP 2 OF 3" with progress dashes (onboarding). */
export function StepHeader({ step, of }: { step: number; of: number }) {
  const { colors } = useTheme();
  return (
    <View style={styles.stepRow} accessibilityLabel={`Step ${step} of ${of}`}>
      <KText variant="label" color="inkMuted">
        Step {step} of {of}
      </KText>
      <View style={styles.dashes}>
        {Array.from({ length: of }, (_, i) => (
          <View key={i} style={[styles.dash, { backgroundColor: i < step ? colors.ki : colors.panelRaised }]} />
        ))}
      </View>
    </View>
  );
}

/** A horizontal 0–100 meter in the energy color (emphasis bars, progress). */
export function Meter({ value, label }: { value: number; label: string }) {
  const { colors } = useTheme();
  const pct = Math.max(0, Math.min(100, value));
  return (
    <View style={styles.meterRow} accessibilityLabel={`${label} ${pct} out of 100`}>
      <KText variant="label" color="inkMuted" style={styles.meterLabel}>
        {label}
      </KText>
      <View style={[styles.meterTrack, { backgroundColor: colors.panelRaised }]}>
        <View style={[styles.meterFill, { width: `${pct}%`, backgroundColor: colors.ki }]} />
      </View>
    </View>
  );
}

/** Darker shade of a #rrggbb color for the button's pressed depth. */
function shade(hex: string, f = 0.45): string {
  const n = parseInt(hex.slice(1), 16);
  const c = (s: number) => Math.round(((n >> s) & 255) * f);
  return `rgb(${c(16)}, ${c(8)}, ${c(0)})`;
}

const styles = StyleSheet.create({
  panel: { borderWidth: 1, borderRadius: radius.lg, padding: spacing[4] },
  primaryWrap: { alignSelf: 'stretch' },
  primaryDepth: { borderRadius: radius.lg, minHeight: 58 },
  primary: { minHeight: 52, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing[4] },
  primaryText: { textAlign: 'center' },
  ghost: { minHeight: 48, borderWidth: 1, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center' },
  stepRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  dashes: { flexDirection: 'row', gap: spacing[2] },
  dash: { width: 24, height: 4, borderRadius: 2 },
  meterRow: { flexDirection: 'row', alignItems: 'center', gap: spacing[3] },
  meterLabel: { width: 64 },
  meterTrack: { flex: 1, height: 6, borderRadius: 3, overflow: 'hidden' },
  meterFill: { height: 6, borderRadius: 3 },
});
