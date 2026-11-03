import type { ReactNode } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { useTheme } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

export function PlaceholderScreen({ title, note, children }: { title: string; note: string; children?: ReactNode }) {
  const { colors } = useTheme();
  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]} edges={['top']}>
      <ScrollView contentContainerStyle={styles.body}>
        <KText variant="label" color="inkFaint">
          Ki Forge
        </KText>
        <KText variant="screenTitle" accessibilityRole="header">
          {title}
        </KText>
        <KText color="inkMuted">{note}</KText>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  body: { flexGrow: 1, padding: spacing[4], gap: spacing[2], justifyContent: 'center' },
});
