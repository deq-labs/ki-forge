import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, type ReactNode } from 'react';

import { ApiError } from '@/lib/api';
import { useMe } from '@/lib/queries';
import { useSyncLoop } from '@/lib/use-sync-loop';
import { useSettings } from '@/state/settings';
import { fontAssets } from '@/theme/fonts';
import { isPathSlug, PathThemeProvider, useTheme } from '@/theme/theme';

SplashScreen.preventAutoHideAsync().catch(() => {});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});

/** Re-points ki / kiHot to the signed-in user's path once /v1/me answers. */
function PathTheme({ children }: { children: ReactNode }) {
  const me = useMe();
  const slug = me.data?.enrollment?.path_slug;
  return <PathThemeProvider path={isPathSlug(slug) ? slug : 'storm'}>{children}</PathThemeProvider>;
}

function Navigator() {
  const { colors } = useTheme();
  const signedIn = useSettings((s) => !!s.devEmail);
  useSyncLoop();
  const navTheme = useMemo(
    () => ({
      ...DarkTheme,
      colors: {
        ...DarkTheme.colors,
        background: colors.night900,
        card: colors.night900,
        text: colors.ink,
        border: colors.line,
        primary: colors.ki,
      },
    }),
    [colors],
  );
  return (
    <ThemeProvider value={navTheme}>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.night900 } }}>
        <Stack.Protected guard={signedIn}>
          <Stack.Screen name="(tabs)" />
        </Stack.Protected>
        <Stack.Protected guard={!signedIn}>
          <Stack.Screen name="sign-in" />
        </Stack.Protected>
      </Stack>
    </ThemeProvider>
  );
}

export default function RootLayout() {
  const [loaded, error] = useFonts(fontAssets);

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync().catch(() => {});
  }, [loaded, error]);

  if (!loaded && !error) return null;

  return (
    <QueryClientProvider client={queryClient}>
      <PathTheme>
        <Navigator />
      </PathTheme>
    </QueryClientProvider>
  );
}

