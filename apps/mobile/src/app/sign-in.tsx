import { useSignIn, useSignUp } from '@clerk/expo';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { KText } from '@/components/k-text';
import { GhostButton, PrimaryButton } from '@/components/ui';
import { clerkEnabled, clerkErrorCode, clerkErrorMessage } from '@/lib/auth';
import { apiUrl, isEmail, useSettings } from '@/state/settings';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

/** Sign in or sign up: Clerk email codes when configured, else the local dev sign-in. */
export default function SignIn() {
  return clerkEnabled ? <EmailCodeSignIn /> : <DevSignIn />;
}

type Step = { kind: 'email' } | { kind: 'code'; email: string; mode: 'signIn' | 'signUp' };

/**
 * One screen for new and returning athletes: enter an email, get a 6-digit code, type it in. An email
 * Clerk doesn't know yet becomes a new account (#78). No passwords.
 */
function EmailCodeSignIn() {
  const { colors } = useTheme();
  const { signIn } = useSignIn();
  const { signUp } = useSignUp();
  const [step, setStep] = useState<Step>({ kind: 'email' });
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(clerkErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const sendCode = (address: string) =>
    run(async () => {
      const clean = address.trim().toLowerCase();
      const sent = await signIn.emailCode.sendCode({ emailAddress: clean });
      if (!sent.error) {
        setStep({ kind: 'code', email: clean, mode: 'signIn' });
        return;
      }
      if (clerkErrorCode(sent.error) !== 'form_identifier_not_found') throw sent.error;
      // New here: create the account, then verify the same way.
      const created = await signUp.create({ emailAddress: clean });
      if (created.error) throw created.error;
      const mailed = await signUp.verifications.sendEmailCode();
      if (mailed.error) throw mailed.error;
      setStep({ kind: 'code', email: clean, mode: 'signUp' });
    });

  const verify = (s: Extract<Step, { kind: 'code' }>) =>
    run(async () => {
      const digits = code.replace(/\D/g, '');
      if (s.mode === 'signIn') {
        const r = await signIn.emailCode.verifyCode({ code: digits });
        if (r.error) throw r.error;
        if (signIn.status !== 'complete') throw new Error(`Sign-in needs another step (${signIn.status}).`);
        const f = await signIn.finalize();
        if (f.error) throw f.error;
      } else {
        const r = await signUp.verifications.verifyEmailCode({ code: digits });
        if (r.error) throw r.error;
        if (signUp.status !== 'complete') {
          // The Clerk dashboard asks for more than an email (e.g. a password or a name).
          const missing = signUp.missingFields.join(', ') || signUp.status;
          throw new Error(`Sign-up needs more details (${missing}). Turn those off in Clerk.`);
        }
        const f = await signUp.finalize();
        if (f.error) throw f.error;
      }
      // ClerkSession picks up the new session and opens the app.
    });

  const inputStyle = [
    textStyle('body'),
    styles.input,
    { color: colors.ink, backgroundColor: colors.panel, borderColor: colors.line },
  ];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <KeyboardAvoidingView style={styles.body} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <KText variant="label" color="inkFaint">
          Ki Forge
        </KText>
        {step.kind === 'email' ? (
          <>
            <KText variant="screenTitle" accessibilityRole="header">
              Enter the arena
            </KText>
            <KText color="inkMuted">
              New or returning, use your email. We&apos;ll send a 6-digit code; no password to remember.
            </KText>
            <TextInput
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor={colors.inkFaint}
              autoCapitalize="none"
              autoComplete="email"
              textContentType="emailAddress"
              keyboardType="email-address"
              inputMode="email"
              returnKeyType="send"
              onSubmitEditing={() => isEmail(email) && !busy && sendCode(email)}
              accessibilityLabel="Email"
              style={inputStyle}
            />
            <PrimaryButton
              label={busy ? 'Sending…' : isEmail(email) ? 'Send my code' : 'Enter your email'}
              disabled={!isEmail(email) || busy}
              onPress={() => sendCode(email)}
            />
          </>
        ) : (
          <>
            <KText variant="screenTitle" accessibilityRole="header">
              Check your email
            </KText>
            <KText color="inkMuted">
              {step.mode === 'signUp' ? 'Welcome! ' : ''}We sent a 6-digit code to {step.email}.
            </KText>
            <TextInput
              value={code}
              onChangeText={(v) => setCode(v.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456"
              placeholderTextColor={colors.inkFaint}
              autoComplete="one-time-code"
              textContentType="oneTimeCode"
              keyboardType="number-pad"
              inputMode="numeric"
              maxLength={6}
              returnKeyType="go"
              onSubmitEditing={() => code.length === 6 && !busy && verify(step)}
              accessibilityLabel="6-digit code"
              style={[inputStyle, textStyle('dataSm'), styles.code]}
            />
            <PrimaryButton
              label={busy ? 'Checking…' : 'Sign in'}
              disabled={code.length !== 6 || busy}
              onPress={() => verify(step)}
            />
            <View style={styles.row}>
              <View style={styles.flex}>
                <GhostButton
                  label="Send a new code"
                  onPress={() =>
                    void run(async () => {
                      const r =
                        step.mode === 'signIn'
                          ? await signIn.emailCode.sendCode()
                          : await signUp.verifications.sendEmailCode();
                      if (r.error) throw r.error;
                      setNotice(`New code sent to ${step.email}.`);
                    })
                  }
                />
              </View>
              <View style={styles.flex}>
                <GhostButton
                  label="Different email"
                  onPress={() => {
                    void signIn.reset();
                    setCode('');
                    setNotice(null);
                    setError(null);
                    setStep({ kind: 'email' });
                  }}
                />
              </View>
            </View>
            {notice && !error ? (
              <KText variant="caption" color="inkMuted" accessibilityLiveRegion="polite">
                {notice}
              </KText>
            ) : null}
          </>
        )}
        {error ? (
          <KText variant="caption" color="danger" accessibilityRole="alert">
            {error}
          </KText>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

/**
 * Dev sign-in: "Who's training?". The email is sent as `X-Dev-User` to the API on Joe's PC, which
 * creates the account on first use. Used only when no Clerk key is configured.
 */
function DevSignIn() {
  const { colors } = useTheme();
  const signIn = useSettings((s) => s.signIn);
  const [email, setEmail] = useState('');
  const valid = isEmail(email);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]}>
      <KeyboardAvoidingView style={styles.body} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <KText variant="label" color="inkFaint">
          Ki Forge · dev sign-in
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
  flex: { flex: 1 },
  body: { flex: 1, padding: spacing[4], gap: spacing[3], justifyContent: 'center' },
  input: { minHeight: 52, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing[4] },
  code: { fontSize: 28, letterSpacing: 8, textAlign: 'center' },
  row: { flexDirection: 'row', gap: spacing[3] },
  button: { minHeight: 52, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center' },
  footer: { marginTop: spacing[4] },
});
