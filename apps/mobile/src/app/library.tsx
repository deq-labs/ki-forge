import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ExercisePhotos } from '@/components/exercise-photos';
import { KText } from '@/components/k-text';
import { GhostButton, Panel } from '@/components/ui';
import { ApiError, type LibraryExercise } from '@/lib/api';
import { useLibrary } from '@/lib/queries';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

const PAGE = 40;
const MUSCLES = [
  'chest',
  'shoulders',
  'lats',
  'middle back',
  'biceps',
  'triceps',
  'quadriceps',
  'hamstrings',
  'glutes',
  'calves',
  'abdominals',
];

/** Browse the exercise library (free-exercise-db): search by name, filter by muscle, tap for photos and steps. */
export default function Library() {
  const { colors } = useTheme();
  const router = useRouter();
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [muscle, setMuscle] = useState<string | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState<string | null>(null);

  // Search after a short pause in typing, from the first page.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(text.trim());
      setLimit(PAGE);
    }, 250);
    return () => clearTimeout(t);
  }, [text]);

  const lib = useLibrary(q, muscle, limit);
  const items = lib.data?.items ?? [];
  const offline = lib.error instanceof ApiError && lib.error.offline;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <KText variant="screenTitle" accessibilityRole="header">
          Exercise library
        </KText>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder="Search, e.g. dumbbell row"
          placeholderTextColor={colors.inkFaint}
          accessibilityLabel="Search exercises"
          autoCorrect={false}
          returnKeyType="search"
          style={[
            textStyle('body'),
            styles.search,
            {
              color: colors.ink,
              backgroundColor: colors.night800,
              borderColor: colors.line,
            },
          ]}
        />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
          {MUSCLES.map((m) => {
            const on = muscle === m;
            return (
              <Pressable
                key={m}
                onPress={() => {
                  setMuscle(on ? null : m);
                  setLimit(PAGE);
                }}
                accessibilityRole="button"
                accessibilityState={{ selected: on }}
                accessibilityLabel={`Filter: ${m}`}
                style={[
                  styles.chip,
                  {
                    borderColor: on ? colors.volt : colors.line,
                    backgroundColor: on ? colors.night800 : 'transparent',
                  },
                ]}>
                <KText variant="caption" color={on ? 'volt' : 'inkMuted'}>
                  {on ? `✓ ${m}` : m}
                </KText>
              </Pressable>
            );
          })}
        </ScrollView>

        {lib.data ? (
          <KText variant="caption" color="inkMuted" accessibilityLiveRegion="polite">
            {lib.data.total} {lib.data.total === 1 ? 'exercise' : 'exercises'}
          </KText>
        ) : null}
        {offline ? <KText color="inkMuted">The library needs a connection.</KText> : null}
        {lib.isPending ? <ActivityIndicator color={colors.ki} style={styles.loading} /> : null}

        <Panel style={styles.list}>
          {items.map((e, i) => (
            <Row
              key={e.id}
              e={e}
              first={i === 0}
              open={open === e.id}
              onToggle={() => setOpen(open === e.id ? null : e.id)}
            />
          ))}
          {lib.data && !items.length ? (
            <KText color="inkMuted" style={styles.empty}>
              Nothing matches. Try fewer words.
            </KText>
          ) : null}
        </Panel>
        {lib.data && items.length < lib.data.total ? (
          <GhostButton label="Show more" onPress={() => setLimit((l) => l + PAGE)} />
        ) : null}

        <KText variant="caption" color="inkFaint">
          Exercise photos and instructions: free-exercise-db (public domain).
        </KText>
        <GhostButton label="Back" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({
  e,
  first,
  open,
  onToggle,
}: {
  e: LibraryExercise;
  first: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const { colors } = useTheme();
  const detail = [e.equipment, e.primary_muscles.join(', ')].filter(Boolean).join(' · ');
  return (
    <View style={[!first && { borderTopColor: colors.line, borderTopWidth: 1 }]}>
      <Pressable
        onPress={onToggle}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`${e.name}${e.program_exercise ? ', in your program' : ''}. ${detail}`}
        style={styles.row}>
        {e.images[0] ? (
          <Image source={{ uri: e.images[0] }} style={[styles.thumb, { backgroundColor: colors.night800 }]} />
        ) : (
          <View style={[styles.thumb, { backgroundColor: colors.night800 }]} />
        )}
        <View style={styles.flex}>
          <KText>{e.name}</KText>
          <KText variant="caption" color="inkMuted">
            {detail}
          </KText>
          {e.program_exercise ? (
            <KText variant="caption" color="volt">
              ● In your program
            </KText>
          ) : null}
        </View>
      </Pressable>
      {open ? (
        <View style={styles.detail}>
          <ExercisePhotos images={e.images} name={e.name} />
          {e.instructions.map((s, i) => (
            <View key={i} style={styles.step}>
              <KText variant="caption" color="volt">
                {i + 1}.
              </KText>
              <KText variant="caption" style={styles.flex}>
                {s}
              </KText>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  body: { padding: spacing[4], gap: spacing[3] },
  loading: { marginTop: spacing[4] },
  search: {
    minHeight: 44,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing[3],
  },
  chips: { gap: spacing[2] },
  chip: {
    minHeight: 44,
    paddingHorizontal: spacing[3],
    borderRadius: radius.pill,
    borderWidth: 1,
    justifyContent: 'center',
  },
  list: { padding: 0 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing[3],
    minHeight: 64,
    padding: spacing[3],
  },
  thumb: { width: 72, height: 48, borderRadius: radius.sm },
  flex: { flex: 1 },
  detail: {
    paddingHorizontal: spacing[3],
    paddingBottom: spacing[3],
    gap: spacing[2],
  },
  step: { flexDirection: 'row', gap: spacing[2] },
  empty: { padding: spacing[3] },
});
