import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { apiUrl, isEmail, useSettings } from '@/state/settings';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/**
 * Dev sign-in: "Who's training?". The email is sent as `X-Dev-User` to the API on Joe's PC, which
 * creates the account on first use. Real sign-in (Clerk) replaces this in M6.
 */
export default function SignIn() {
  const { colors } = useTheme();
  const signIn = useSettings((s) => s.signIn);
  const [email, setEmail] = useState('');
  const valid = isEmail(email);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <KeyboardAvoidingView style={styles.body} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <KText variant="label" color="inkFaint">
          Ki Forge
        </KText>
        <KText variant="screenTitle" accessibilityRole="header">
          Who&apos;s training?
        </KText>
        <KText color="inkMuted">
          Enter your email to start or continue your run. Each email is its own account on this server.
        </KText>
        <TextInput
          value={email}
          onChangeText={setEmail}
          placeholder="you@example.com"
          placeholderTextColor={colors.inkFaint}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          inputMode="email"
          returnKeyType="go"
          onSubmitEditing={() => valid && signIn(email)}
          accessibilityLabel="Email"
          style={[
            textStyle('body'),
            styles.input,
            { color: colors.ink, backgroundColor: colors.panel, borderColor: colors.line },
          ]}
        />
        <Pressable
          onPress={() => signIn(email)}
          disabled={!valid}
          accessibilityRole="button"
          accessibilityState={{ disabled: !valid }}
          style={({ pressed }) => [
            styles.button,
            { backgroundColor: colors.ki, opacity: valid ? 1 : 0.38, transform: [{ translateY: pressed ? 2 : 0 }] },
          ]}>
          <KText variant="cardTitle" color="onKi">
            {valid ? 'Enter the arena' : 'Enter your email'}
          </KText>
        </Pressable>
        <View style={styles.footer}>
          <KText variant="caption" color="inkFaint">
            Server: {apiUrl()}
          </KText>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  body: { flex: 1, padding: spacing[4], gap: spacing[3], justifyContent: 'center' },
  input: { minHeight: 52, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing[4] },
  button: { minHeight: 52, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center' },
  footer: { marginTop: spacing[4] },
});
