import { Tabs } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, radius, shadow, spacing, typography } from '@/theme/tokens';

// M0 placeholder tab bar: Base, Arc, Train (raised center), Scan, Profile. Icons and motion arrive in M3.
export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.night900 },
        tabBarStyle: styles.bar,
        tabBarActiveTintColor: colors.ki,
        tabBarInactiveTintColor: colors.inkMuted,
        tabBarLabelStyle: styles.label,
        tabBarIconStyle: styles.noIcon,
      }}>
      <Tabs.Screen name="index" options={{ title: 'Base' }} />
      <Tabs.Screen name="arc" options={{ title: 'Arc' }} />
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
              <View style={styles.trainButton}>
                <Text style={styles.trainText}>Train</Text>
              </View>
            </Pressable>
          ),
        }}
      />
      <Tabs.Screen name="scan" options={{ title: 'Scan' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: colors.night900,
    borderTopColor: colors.line,
    minHeight: 64,
  },
  label: {
    fontSize: typography.caption.fontSize,
    fontWeight: '700',
  },
  noIcon: { display: 'none' },
  trainSlot: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 44,
    minHeight: 44,
  },
  trainButton: {
    width: 64,
    height: 64,
    marginTop: -spacing[5],
    borderRadius: radius.pill,
    backgroundColor: colors.ki,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: shadow.glow,
  },
  trainText: {
    color: colors.onKi,
    fontWeight: '800',
    fontSize: typography.caption.fontSize,
  },
});
