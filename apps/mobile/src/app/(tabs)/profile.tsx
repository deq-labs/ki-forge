import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { KText } from '@/components/k-text';
import { PlaceholderScreen } from '@/components/placeholder-screen';
import { defaultApiUrl } from '@/lib/config';
import { useSettings } from '@/state/settings';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

// The full Profile screen arrives in M4. For now: who is signed in, the server address, sign out.
export default function ProfileScreen() {
  const { colors } = useTheme();
  const queryClient = useQueryClient();
  const { devEmail, apiUrlOverride, signOut, setApiUrl } = useSettings();
  const [url, setUrl] = useState(apiUrlOverride ?? '');

  return (
    <PlaceholderScreen title="Profile" note="Settings, path change and data export arrive in M4.">
      <KText variant="label" color="inkFaint" style={styles.section}>
        Signed in as
      </KText>
      <KText variant="bodyStrong">{devEmail}</KText>

      <KText variant="label" color="inkFaint" style={styles.section}>
        Server
      </KText>
      <TextInput
        value={url}
        onChangeText={setUrl}
        placeholder={defaultApiUrl()}
        placeholderTextColor={colors.inkFaint}
        autoCapitalize="none"
        autoCorrect={false}
        inputMode="url"
        accessibilityLabel="Server address"
        onEndEditing={() => {
          setApiUrl(url || null);
          queryClient.invalidateQueries();
        }}
        style={[textStyle('dataSm'), styles.input, { color: colors.ink, backgroundColor: colors.panel, borderColor: colors.line }]}
      />
      <KText variant="caption" color="inkFaint">
        Leave empty to use this computer&apos;s address ({defaultApiUrl()}).
      </KText>

      <View style={styles.section}>
        <Pressable
          onPress={() => {
            queryClient.clear();
            signOut();
          }}
          accessibilityRole="button"
          style={[styles.ghost, { borderColor: colors.line }]}>
          <KText variant="bodyStrong">Switch user</KText>
        </Pressable>
      </View>
    </PlaceholderScreen>
  );
}

const styles = StyleSheet.create({
  section: { marginTop: spacing[4] },
  input: { minHeight: 48, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing[3] },
  ghost: { minHeight: 48, borderWidth: 1, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center' },
});
