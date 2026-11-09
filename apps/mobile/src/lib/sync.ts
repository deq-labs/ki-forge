import type { QueryClient } from '@tanstack/react-query';
import { create } from 'zustand';

import { getDb } from '@/db/db';
import { markSynced, pending, pendingCount } from '@/db/repo';
import { api, ApiError, type Me, type SyncResponse } from '@/lib/api';
import { chunkBatch } from '@/lib/batch';
import { useSettings } from '@/state/settings';

/**
 * The sync queue: unsynced sessions and sets in SQLite are posted to POST /v1/sync whenever we can reach
 * the server. The server upserts on client ids and awards idempotently, so retries and replays are safe.
 * Its response is authoritative: stats replace the optimistic numbers on screen.
 */

export type SyncStatus = 'idle' | 'syncing' | 'offline' | 'error';

type SyncState = {
  status: SyncStatus;
  pending: number;
  lastError: string | null;
  /** The latest response that awarded something, for the rewards overlay (#39). Cleared when shown. */
  lastReward: SyncResponse | null;
  clearReward: () => void;
};

export const useSync = create<SyncState>((set) => ({
  status: 'idle',
  pending: 0,
  lastError: null,
  lastReward: null,
  clearReward: () => set({ lastReward: null }),
}));

let running: Promise<SyncResponse | null> | null = null;
let again = false;
let backoffMs = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

/** Push everything unsynced now. Concurrent calls share one run (and queue one more if rows arrived). */
export function syncNow(queryClient: QueryClient): Promise<SyncResponse | null> {
  if (running) {
    again = true;
    return running;
  }
  running = run(queryClient).finally(() => {
    running = null;
    if (again) {
      again = false;
      void syncNow(queryClient);
    }
  });
  return running;
}

/** Sync soon (debounced), e.g. right after a set is logged. */
export function requestSync(queryClient: QueryClient, delayMs = 1_500): void {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    timer = null;
    void syncNow(queryClient);
  }, delayMs);
}

async function run(queryClient: QueryClient): Promise<SyncResponse | null> {
  const owner = useSettings.getState().devEmail;
  if (!owner) return null;
  const db = await getDb();
  const todo = await pending(db, owner);
  if (!todo.sessions.length && !todo.sets.length) {
    useSync.setState({ status: 'idle', pending: 0, lastError: null });
    return null;
  }
  useSync.setState({ status: 'syncing', pending: todo.sessions.length + todo.sets.length });

  let last: SyncResponse | null = null;
  try {
    for (const batch of chunkBatch(todo.sessions, todo.sets)) {
      const res = await api.post('/v1/sync', {
        sessions: batch.sessions.map((s) => ({
          client_id: s.client_id,
          template_code: s.template_code,
          week: s.week,
          garage_mode: s.garage_mode,
          started_at: s.started_at,
          completed_at: s.completed_at,
          short_day: s.short_day ?? undefined,
        })),
        sets: batch.sets.map((s) => ({
          client_id: s.client_id,
          session_client_id: s.session_client_id,
          exercise_slug: s.exercise_slug,
          set_no: s.set_no,
          weight_lb: s.weight_lb,
          reps: s.reps,
          rir: s.rir,
          is_swap: s.is_swap,
          supersedes_client_id: s.supersedes_client_id,
          logged_at: s.logged_at,
          slot: s.slot ?? null,
          seconds: s.seconds ?? null,
          band: s.band ?? null,
        })),
      });
      await markSynced(db, res.accepted.sessions, res.accepted.sets);
      last = res;
      applyStats(queryClient, owner, res);
      if (res.xp_awarded.length || res.level_up || res.new_badges.length) useSync.setState({ lastReward: res });
    }
    backoffMs = 0;
    useSync.setState({ status: 'idle', pending: await pendingCount(db, owner), lastError: null });
    void queryClient.invalidateQueries({ queryKey: ['week', owner] });
    return last;
  } catch (e) {
    const offline = e instanceof ApiError && e.offline;
    useSync.setState({
      status: offline ? 'offline' : 'error',
      pending: await pendingCount(db, owner),
      lastError: e instanceof Error ? e.message : String(e),
    });
    // Retry with backoff (capped at 2 minutes). A 4xx means the batch itself is bad: don't hammer.
    const permanent = e instanceof ApiError && e.status >= 400 && e.status < 500;
    if (!permanent) {
      backoffMs = Math.min(backoffMs ? backoffMs * 2 : 5_000, 120_000);
      requestSync(queryClient, backoffMs);
    }
    return null;
  }
}

/** Replace the cached /v1/me stats with the server's authoritative numbers. */
function applyStats(queryClient: QueryClient, owner: string, res: SyncResponse): void {
  queryClient.setQueryData<Me>(['me', owner], (me) => (me ? { ...me, stats: res.stats } : me));
  if (res.new_badges.length) void queryClient.invalidateQueries({ queryKey: ['me', owner] });
}

export async function refreshPendingCount(): Promise<void> {
  const owner = useSettings.getState().devEmail;
  if (!owner) return;
  useSync.setState({ pending: await pendingCount(await getDb(), owner) });
}
