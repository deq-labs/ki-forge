import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { KText } from '@/components/k-text';
import { Panel } from '@/components/ui';
import { warmupSteps } from '@/lib/warmup';
import { kv } from '@/lib/storage';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

function load(key: string): boolean[] {
  try {
    const raw = kv.get(key);
    return raw ? (JSON.parse(raw) as boolean[]) : [];
  } catch {
    return [];
  }
}

/** The session's warm-up as a checklist (rounds, then ramp sets). Kept on this device; earns no XP. */
export function WarmupChecklist({ text, storageKey }: { text: string; storageKey: string }) {
  const { colors } = useTheme();
  const { detail, steps } = warmupSteps(text);
  const [done, setDone] = useState<boolean[]>(() => load(storageKey));
  const toggle = (i: number) => {
    const next = steps.map((_, j) => (j === i ? !done[j] : !!done[j]));
    setDone(next);
    try {
      kv.set(storageKey, JSON.stringify(next));
    } catch {
      // storage unavailable: the checklist still works for this visit
    }
  };
  const all = steps.length > 0 && steps.every((_, i) => done[i]);

  return (
    <Panel style={styles.panel}>
      <KText variant="label" color={all ? 'good' : 'inkMuted'}>
        {all ? '✓ Warmed up' : 'Warm-up'}
      </KText>
      <KText variant="caption">{detail}</KText>
      <View style={styles.row}>
        {steps.map((s, i) => (
          <Pressable
            key={s}
            onPress={() => toggle(i)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: !!done[i] }}
            style={[
              styles.step,
              {
                borderColor: done[i] ? colors.good : colors.line,
                backgroundColor: done[i] ? `${colors.good}33` : 'transparent',
              },
            ]}>
            <KText variant="caption" color={done[i] ? 'good' : 'ink'}>
              {done[i] ? '✓ ' : ''}
              {s}
            </KText>
          </Pressable>
        ))}
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: { gap: spacing[2] },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing[2] },
  step: {
    minHeight: 44,
    paddingHorizontal: spacing[3],
    borderRadius: radius.md,
    borderWidth: 1.5,
    justifyContent: 'center',
  },
});
