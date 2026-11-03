import { useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { Silhouette } from '@/components/silhouette';
import { Meter, Panel, PrimaryButton, StepHeader } from '@/components/ui';
import { api, ApiError, type Program } from '@/lib/api';
import { useMe, useProgram } from '@/lib/queries';
import { useOnboarding } from '@/state/onboarding';
import { useSettings } from '@/state/settings';
import { isPathSlug, PathThemeProvider, useTheme } from '@/theme/theme';
import { pathColors, radius, spacing, type PathSlug } from '@/theme/tokens';

type ProgramPath = Program['paths'][number];

const AREA_LABEL: Record<string, string> = { delts: 'Delts', back: 'Back', arms: 'Arms', legs: 'Legs', engine: 'Engine' };

/** Path picker: onboarding step 2, and Profile › Change path. Re-themes live as you choose. */
export default function Paths() {
  const program = useProgram();
  const me = useMe();
  const { from } = useLocalSearchParams<{ from?: string }>();
  const onboarding = from === 'onboarding';
  const draft = useOnboarding();
  const current = me.data?.enrollment?.path_slug;
  const [selected, setSelected] = useState<PathSlug>(
    onboarding ? draft.path : isPathSlug(current) ? current : 'storm',
  );

  return (
    <PathThemeProvider path={selected}>
      <PathPicker
        paths={program.data?.paths}
        loading={program.isPending}
        selected={selected}
        onSelect={setSelected}
        onboarding={onboarding}
        enrollmentId={me.data?.enrollment?.id}
      />
    </PathThemeProvider>
  );
}

function PathPicker({
  paths,
  loading,
  selected,
  onSelect,
  onboarding,
  enrollmentId,
}: {
  paths?: ProgramPath[];
  loading: boolean;
  selected: PathSlug;
  onSelect: (p: PathSlug) => void;
  onboarding: boolean;
  enrollmentId?: string;
}) {
  const { colors } = useTheme();
  const router = useRouter();
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail);
  const setPath = useOnboarding((s) => s.setPath);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = paths?.find((p) => p.slug === selected);

  async function confirm() {
    if (!path) return;
    if (onboarding || !enrollmentId) {
      setPath(selected);
      router.push('/onboarding/start-date');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.raw('patch', `/v1/enrollments/${enrollmentId}`, { body: { path_slug: selected } });
      await queryClient.invalidateQueries({ queryKey: ['me', owner] });
      await queryClient.invalidateQueries({ queryKey: ['week', owner] });
      router.back();
    } catch (e) {
      setError(e instanceof ApiError && e.offline ? 'Changing path needs a connection.' : String((e as Error).message));
    } finally {
      setSaving(false);
    }
  }

  const top3 = path
    ? Object.entries(path.emphasis)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
    : [];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <ScrollView contentContainerStyle={styles.body}>
        {onboarding && <StepHeader step={2} of={3} />}
        <KText variant="screenTitle" accessibilityRole="header">
          Who are you training to become?
        </KText>
        <KText color="inkMuted">
          Every path runs the same core program. Your path sets the focus lifts, your frame target and your aura.
        </KText>

        {loading && <ActivityIndicator color={colors.ki} style={styles.loading} />}
        <View style={styles.grid}>
          {paths?.map((p) => {
            const slug = p.slug as PathSlug;
            const on = slug === selected;
            const pc = pathColors[slug] ?? pathColors.storm;
            return (
              <Pressable
                key={p.slug}
                onPress={() => onSelect(slug)}
                accessibilityRole="radio"
                accessibilityState={{ checked: on }}
                accessibilityLabel={`${p.name}. ${p.tagline}`}
                style={[
                  styles.card,
                  {
                    backgroundColor: colors.panel,
                    borderColor: on ? pc.ki : colors.line,
                    boxShadow: on ? `0 0 18px ${pc.ki}88` : undefined,
                  },
                ]}>
                <View style={[styles.art, { backgroundColor: colors.night800 }]}>
                  <Silhouette ratio={p.ratio_target} color={pc.kiHot} glow={pc.ki} size={96} />
                </View>
                <KText variant="cardTitle">{p.name}</KText>
                <KText variant="caption" color="inkMuted">
                  {p.tagline}
                </KText>
                {on && (
                  <KText variant="label" color="kiHot" style={styles.active}>
                    ✓ Selected
                  </KText>
                )}
              </Pressable>
            );
          })}
        </View>

        {path && (
          <Panel style={styles.detail}>
            <View style={styles.detailHead}>
              <KText variant="cardTitle">{path.name}</KText>
              <KText variant="dataSm" color="inkMuted">
                Frame target {path.ratio_target.toFixed(2)}
              </KText>
            </View>
            <KText variant="caption" color="inkMuted">
              {path.build}
            </KText>
            {top3.map(([area, v]) => (
              <Meter key={area} label={AREA_LABEL[area] ?? area} value={v} />
            ))}
          </Panel>
        )}
        {error && (
          <KText color="danger" accessibilityRole="alert">
            {error}
          </KText>
        )}
      </ScrollView>
      <View style={styles.footer}>
        <PrimaryButton
          label={saving ? 'Saving…' : path ? `Begin as ${path.name}` : 'Loading paths…'}
          onPress={confirm}
          disabled={!path || saving}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  body: { padding: spacing[4], gap: spacing[3] },
  loading: { marginTop: spacing[5] },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[3], marginTop: spacing[2] },
  card: { flexBasis: '47%', flexGrow: 1, borderWidth: 2, borderRadius: radius.lg, padding: spacing[3], gap: spacing[1] },
  art: { borderRadius: radius.md, alignItems: 'center', paddingVertical: spacing[2], marginBottom: spacing[2] },
  active: { marginTop: spacing[1] },
  detail: { gap: spacing[2] },
  detailHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  footer: { padding: spacing[4] },
});
