import { Tabs } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ArcIcon, BarbellIcon, PersonIcon, ScanIcon, StarIcon } from '@/components/icons';
import { KText } from '@/components/k-text';
import { RestTimer, Toasts } from '@/components/rest-timer';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

// Base, Arc, Train (raised center button), Scan, Profile.
export default function TabLayout() {
  const theme = useTheme();
  const { colors } = theme;
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.root}>
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.night900 },
        tabBarStyle: [styles.bar, { backgroundColor: colors.night900, borderTopColor: colors.line }],
        tabBarActiveTintColor: colors.ki,
        tabBarInactiveTintColor: colors.inkMuted,
        tabBarLabelStyle: [textStyle('caption'), styles.label],
        tabBarItemStyle: styles.item,
      }}>
      <Tabs.Screen
        name="index"
        options={{ title: 'Base', tabBarIcon: ({ color }) => <StarIcon color={color} /> }}
      />
      <Tabs.Screen name="arc" options={{ title: 'Arc', tabBarIcon: ({ color }) => <ArcIcon color={color} /> }} />
      <Tabs.Screen
        name="train"
        options={{
          title: 'Train',
          tabBarButton: ({ onPress, accessibilityState }) => (
            <Pressable
              onPress={onPress}
              accessibilityRole="tab"
              accessibilityLabel="Train"
              accessibilityState={accessibilityState}
              style={styles.trainSlot}>
              <View style={[styles.trainButton, { backgroundColor: colors.ki, boxShadow: theme.style.glow ? `0 0 18px ${colors.ki}aa` : undefined }]}>
                <BarbellIcon color={colors.onKi} size={30} />
              </View>
              <KText variant="caption" color={accessibilityState?.selected ? 'ink' : 'inkMuted'} style={styles.label}>
                Train
              </KText>
            </Pressable>
          ),
        }}
      />
      <Tabs.Screen name="scan" options={{ title: 'Scan', tabBarIcon: ({ color }) => <ScanIcon color={color} /> }} />
      <Tabs.Screen
        name="profile"
        options={{ title: 'Profile', tabBarIcon: ({ color }) => <PersonIcon color={color} /> }}
      />
    </Tabs>
      {/* Global overlays sit just above the tab bar. */}
      <View pointerEvents="box-none" style={[styles.overlay, { bottom: 72 + insets.bottom }]}>
        <Toasts />
        <RestTimer />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  overlay: { position: 'absolute', left: 0, right: 0, height: 0 },
  bar: { minHeight: 72, paddingTop: spacing[1] },
  item: { minHeight: 48 },
  label: { fontFamily: 'MPLUS1p_700Bold' },
  trainSlot: { flex: 1, alignItems: 'center', justifyContent: 'flex-start', minWidth: 64, minHeight: 48 },
  trainButton: {
    width: 64,
    height: 64,
    marginTop: -spacing[5],
    marginBottom: 2,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
