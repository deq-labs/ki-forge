import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

/** Haptics from the design system: light on a logged set, success on a cleared quest, heavy on level up. */
const enabled = Platform.OS !== 'web';

export const haptic = {
  set: () => enabled && void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {}),
  cleared: () => enabled && void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}),
  levelUp: () => enabled && void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {}),
  restDone: () => enabled && void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {}),
};
