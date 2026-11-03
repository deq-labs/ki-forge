import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { AppState } from 'react-native';

import { refreshPendingCount, syncNow, useSync } from '@/lib/sync';
import { useSettings } from '@/state/settings';

const POLL_MS = 30_000;

/** Keeps the queue draining: on sign-in, when the app comes to the foreground, and every 30 s while rows wait. */
export function useSyncLoop(): void {
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail);

  useEffect(() => {
    if (!owner) return;
    void refreshPendingCount().then(() => syncNow(queryClient));
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') void syncNow(queryClient);
    });
    const interval = setInterval(() => {
      if (useSync.getState().pending > 0) void syncNow(queryClient);
    }, POLL_MS);
    return () => {
      sub.remove();
      clearInterval(interval);
    };
  }, [owner, queryClient]);
}
