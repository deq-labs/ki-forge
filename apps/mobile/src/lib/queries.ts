import { useQuery } from '@tanstack/react-query';

import { getDb } from '@/db/db';
import { cacheGet, cachePut } from '@/db/repo';
import { api, ApiError, type Arc, type Me, type Program, type Week } from '@/lib/api';
import { useSettings } from '@/state/settings';

/**
 * Server reads with an offline fallback: every successful response is cached in SQLite, and when the
 * server can't be reached the last cached copy is returned instead. That is how Train works offline
 * without porting the rules engine to the app (CLAUDE.md rule 1).
 */
async function cached<T>(owner: string, key: string, fetcher: () => Promise<T>): Promise<T> {
  try {
    const fresh = await fetcher();
    void getDb()
      .then((db) => cachePut(db, owner, key, fresh))
      .catch(() => {});
    return fresh;
  } catch (e) {
    if (e instanceof ApiError && e.offline) {
      const copy = await getDb()
        .then((db) => cacheGet<T>(db, owner, key))
        .catch(() => null);
      if (copy) return copy;
    }
    throw e;
  }
}

/** The signed-in user, run and stats. Keyed by identity so switching dev users never mixes data. */
export function useMe() {
  const owner = useSettings((s) => s.devEmail);
  return useQuery<Me>({
    queryKey: ['me', owner],
    queryFn: () => cached(owner!, 'me', () => api.get('/v1/me')),
    enabled: !!owner,
  });
}

export function useProgram() {
  const owner = useSettings((s) => s.devEmail);
  return useQuery<Program>({
    queryKey: ['program'],
    queryFn: () => cached(owner ?? 'anon', 'program', () => api.get('/v1/program')),
    staleTime: 60 * 60 * 1000,
  });
}

/** A built week (default: the current one). The next week is prefetched into the cache too. */
export function useWeek(week?: number, enabled = true) {
  const owner = useSettings((s) => s.devEmail);
  return useQuery<Week>({
    queryKey: ['week', owner, week ?? 'current'],
    queryFn: async () => {
      const key = week === undefined ? 'week:current' : `week:${week}`;
      const data = await cached(owner!, key, () => api.get('/v1/week', { query: { week } }));
      if (week === undefined) {
        // Also file it under its number, and fetch next week for offline use (best effort).
        void getDb().then((db) => cachePut(db, owner!, `week:${data.week}`, data)).catch(() => {});
        void cached(owner!, `week:${data.week + 1}`, () => api.get('/v1/week', { query: { week: data.week + 1 } })).catch(
          () => {},
        );
      }
      return data;
    },
    enabled: !!owner && enabled,
  });
}

/** Phases with dates and status, plus progress through the current week. */
export function useArc() {
  const owner = useSettings((s) => s.devEmail);
  return useQuery<Arc>({
    queryKey: ['arc', owner],
    queryFn: () => cached(owner!, 'arc', () => api.get('/v1/arc')),
    enabled: !!owner,
  });
}

/** Every Trial of the active run with whatever results are entered. */
export function useTrials() {
  const owner = useSettings((s) => s.devEmail);
  return useQuery({
    queryKey: ['trials', owner],
    queryFn: () => cached(owner!, 'trials', () => api.get('/v1/trials')),
    enabled: !!owner,
  });
}
