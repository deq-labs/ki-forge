import { useEffect, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

/** Drifting energy particles around the Base silhouette, in the path's colors. Nothing under reduced motion. */
export function Aura({ colors, count = 9 }: { colors: [string, string]; count?: number }) {
  const reduceMotion = useReducedMotion();
  // Deterministic layout so it doesn't reshuffle on every render.
  const dots = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => {
        const t = (i * 0.618) % 1;
        return {
          left: `${10 + ((i * 37) % 80)}%` as const,
          top: `${30 + ((i * 53) % 60)}%` as const,
          size: 8 + Math.round(t * 18),
          color: i % 3 === 0 ? colors[1] : colors[0],
          delay: i * 350,
          rise: 18 + Math.round(t * 30),
        };
      }),
    [count, colors],
  );
  if (reduceMotion) return null;
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {dots.map((d, i) => (
        <Dot key={i} {...d} />
      ))}
    </View>
  );
}

function Dot({
  left,
  top,
  size,
  color,
  delay,
  rise,
}: {
  left: `${number}%`;
  top: `${number}%`;
  size: number;
  color: string;
  delay: number;
  rise: number;
}) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withDelay(delay, withRepeat(withTiming(1, { duration: 3200, easing: Easing.inOut(Easing.sin) }), -1, true));
  }, [delay, t]);
  const style = useAnimatedStyle(() => ({
    opacity: 0.35 + 0.45 * t.value,
    transform: [{ translateY: -rise * t.value }, { scale: 0.8 + 0.3 * t.value }],
  }));
  return (
    <Animated.View
      style={[
        { position: 'absolute', left, top, width: size, height: size, borderRadius: size / 2, backgroundColor: color },
        style,
      ]}
    />
  );
}
