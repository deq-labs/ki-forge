import { useEffect, useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';
import { useReducedMotion } from 'react-native-reanimated';

import { KText } from '@/components/k-text';
import { useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** How long each frame shows when the start and end photos alternate. */
export const FRAME_MS = 1200;

/**
 * Exercise photos from the library (free-exercise-db): the start and end position. They alternate like a
 * slow two-frame loop; under reduced motion both frames sit side by side instead.
 */
export function ExercisePhotos({ images, name, compact }: { images?: string[]; name: string; compact?: boolean }) {
  const { colors } = useTheme();
  const reduceMotion = useReducedMotion();
  const [frame, setFrame] = useState(0);
  const [failed, setFailed] = useState(false);
  const frames = (images ?? []).slice(0, 2);
  const animate = frames.length > 1 && !reduceMotion;
  const key = frames.join(' ');

  useEffect(() => {
    // Load both frames up front so the loop never flashes an empty box.
    for (const uri of key.split(' ').filter(Boolean)) void Image.prefetch(uri).catch(() => {});
  }, [key]);

  useEffect(() => {
    if (!animate) return;
    const t = setInterval(() => setFrame((f) => (f + 1) % frames.length), FRAME_MS);
    return () => clearInterval(t);
  }, [animate, frames.length]);

  if (!frames.length || failed) return null;
  const label = `Photos of ${name}: start and end position`;
  const shown = animate ? [frames[frame]] : frames;
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={label} style={styles.wrap}>
      <View style={styles.row}>
        {shown.map((uri, i) => (
          <Image
            key={animate ? 'loop' : uri}
            source={{ uri }}
            onError={() => setFailed(true)}
            resizeMode="cover"
            style={[
              styles.photo,
              compact && styles.compact,
              { backgroundColor: colors.night800, borderColor: colors.line },
              !animate && i > 0 && { marginLeft: spacing[2] },
            ]}
          />
        ))}
      </View>
      {animate ? (
        <KText variant="caption" color="inkFaint">
          {frame === 0 ? 'Start' : 'End'}
        </KText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing[1] },
  row: { flexDirection: 'row' },
  photo: {
    flex: 1,
    aspectRatio: 1.5,
    borderRadius: radius.md,
    borderWidth: 1,
    maxWidth: 360,
  },
  compact: { maxWidth: 220 },
});
