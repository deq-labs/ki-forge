import type { SQLiteDatabase } from 'expo-sqlite';

import { uuid4 } from '@/lib/uuid';

/** A logged session on the device (mirrors the sync payload). */
export type LocalSession = {
  client_id: string;
  template_code: string;
  week: number;
  garage_mode: boolean;
  started_at: string;
  completed_at: string | null;
  synced: boolean;
};

/** A logged set row. Edits are new rows that supersede an older one (append-only). */
export type LocalSet = {
  client_id: string;
  session_client_id: string;
  exercise_slug: string;
  set_no: number;
  weight_lb: number;
  reps: number | null;
  rir: number | null;
  is_swap: boolean;
  supersedes_client_id: string | null;
  logged_at: string;
  synced: boolean;
  /** The session row's key for a block round ("p0"); null for plain rows. */
  slot: string | null;
  /** Seconds: a timed movement's hold, or the time a for-time round was finished at. */
  seconds: number | null;
  /** The band of an X3 set. */
  band: string | null;
};

type SessionRow = Omit<LocalSession, 'garage_mode' | 'synced'> & { garage_mode: number; synced: number };
type SetRow = Omit<LocalSet, 'is_swap' | 'synced'> & { is_swap: number; synced: number };

const toSession = (r: SessionRow): LocalSession => ({ ...r, garage_mode: !!r.garage_mode, synced: !!r.synced });
const toSet = (r: SetRow): LocalSet => ({ ...r, is_swap: !!r.is_swap, synced: !!r.synced });
const now = () => new Date().toISOString();

export async function findSession(
  db: SQLiteDatabase,
  owner: string,
  week: number,
  templateCode: string,
): Promise<LocalSession | null> {
  const row = await db.getFirstAsync<SessionRow>(
    'SELECT * FROM sessions WHERE owner = ? AND week = ? AND template_code = ? ORDER BY started_at DESC LIMIT 1',
    owner,
    week,
    templateCode,
  );
  return row ? toSession(row) : null;
}

/** The session for this week's template, created on first use. */
export async function ensureSession(
  db: SQLiteDatabase,
  owner: string,
  s: { template_code: string; week: number; garage_mode: boolean },
): Promise<LocalSession> {
  const existing = await findSession(db, owner, s.week, s.template_code);
  if (existing) {
    if (existing.garage_mode !== s.garage_mode && !existing.synced) {
      await db.runAsync(
        'UPDATE sessions SET garage_mode = ? WHERE client_id = ?',
        s.garage_mode ? 1 : 0,
        existing.client_id,
      );
      return { ...existing, garage_mode: s.garage_mode };
    }
    return existing;
  }
  const session: LocalSession = { client_id: uuid4(), ...s, started_at: now(), completed_at: null, synced: false };
  await db.runAsync(
    'INSERT INTO sessions (client_id, owner, template_code, week, garage_mode, started_at) VALUES (?, ?, ?, ?, ?, ?)',
    session.client_id,
    owner,
    s.template_code,
    s.week,
    s.garage_mode ? 1 : 0,
    session.started_at,
  );
  return session;
}

export async function completeSession(db: SQLiteDatabase, clientId: string): Promise<void> {
  // Re-marks it unsynced so the completion time reaches the server on the next sync.
  await db.runAsync(
    'UPDATE sessions SET completed_at = COALESCE(completed_at, ?), synced = 0 WHERE client_id = ?',
    now(),
    clientId,
  );
}

export type NewSet = Pick<LocalSet, 'exercise_slug' | 'set_no' | 'weight_lb' | 'reps' | 'rir' | 'is_swap'> & {
  slot?: string | null;
  seconds?: number | null;
  band?: string | null;
};

/** Log a set (or, with `supersedes`, an edit of an earlier set). Written locally before any network call. */
export async function logSet(
  db: SQLiteDatabase,
  owner: string,
  sessionClientId: string,
  set: NewSet,
  supersedes: string | null = null,
): Promise<LocalSet> {
  const row: LocalSet = {
    client_id: uuid4(),
    session_client_id: sessionClientId,
    ...set,
    slot: set.slot ?? null,
    seconds: set.seconds ?? null,
    band: set.band ?? null,
    supersedes_client_id: supersedes,
    logged_at: now(),
    synced: false,
  };
  await db.runAsync(
    `INSERT INTO sets (client_id, owner, session_client_id, exercise_slug, set_no, weight_lb, reps, rir, is_swap,
                       supersedes_client_id, logged_at, slot, seconds, band)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    row.client_id,
    owner,
    sessionClientId,
    set.exercise_slug,
    set.set_no,
    set.weight_lb,
    set.reps,
    set.rir,
    set.is_swap ? 1 : 0,
    supersedes,
    row.logged_at,
    row.slot,
    row.seconds,
    row.band,
  );
  return row;
}

/** The current version of every set in a session: rows nothing supersedes, in log order. */
export async function currentSets(db: SQLiteDatabase, sessionClientId: string): Promise<LocalSet[]> {
  const rows = await db.getAllAsync<SetRow>(
    `SELECT * FROM sets s
     WHERE s.session_client_id = ?
       AND NOT EXISTS (SELECT 1 FROM sets e WHERE e.supersedes_client_id = s.client_id)
     ORDER BY s.logged_at, s.set_no`,
    sessionClientId,
  );
  return rows.map(toSet);
}

export type Pending = { sessions: LocalSession[]; sets: LocalSet[] };

export async function pending(db: SQLiteDatabase, owner: string): Promise<Pending> {
  const sessions = await db.getAllAsync<SessionRow>(
    'SELECT * FROM sessions WHERE owner = ? AND synced = 0 ORDER BY started_at',
    owner,
  );
  const sets = await db.getAllAsync<SetRow>(
    'SELECT * FROM sets WHERE owner = ? AND synced = 0 ORDER BY logged_at',
    owner,
  );
  return { sessions: sessions.map(toSession), sets: sets.map(toSet) };
}

export async function pendingCount(db: SQLiteDatabase, owner: string): Promise<number> {
  const row = await db.getFirstAsync<{ n: number }>(
    'SELECT (SELECT COUNT(*) FROM sessions WHERE owner = ? AND synced = 0) + (SELECT COUNT(*) FROM sets WHERE owner = ? AND synced = 0) AS n',
    owner,
    owner,
  );
  return row?.n ?? 0;
}

export async function markSynced(db: SQLiteDatabase, sessionIds: string[], setIds: string[]): Promise<void> {
  await db.withTransactionAsync(async () => {
    for (const id of sessionIds) await db.runAsync('UPDATE sessions SET synced = 1 WHERE client_id = ?', id);
    for (const id of setIds) await db.runAsync('UPDATE sets SET synced = 1 WHERE client_id = ?', id);
  });
}

// --- cached API responses (offline reads) -----------------------------------------------------------------

export async function cachePut(db: SQLiteDatabase, owner: string, key: string, value: unknown): Promise<void> {
  await db.runAsync(
    'INSERT INTO cache (owner, key, json, fetched_at) VALUES (?, ?, ?, ?) ON CONFLICT(owner, key) DO UPDATE SET json = excluded.json, fetched_at = excluded.fetched_at',
    owner,
    key,
    JSON.stringify(value),
    now(),
  );
}

export async function cacheGet<T>(db: SQLiteDatabase, owner: string, key: string): Promise<T | null> {
  const row = await db.getFirstAsync<{ json: string }>(
    'SELECT json FROM cache WHERE owner = ? AND key = ?',
    owner,
    key,
  );
  return row ? (JSON.parse(row.json) as T) : null;
}

/** Remove everything stored on this device for one identity (account deletion). */
export async function deleteOwner(db: SQLiteDatabase, owner: string): Promise<void> {
  await db.withTransactionAsync(async () => {
    await db.runAsync('DELETE FROM sets WHERE owner = ?', owner);
    await db.runAsync('DELETE FROM sessions WHERE owner = ?', owner);
    await db.runAsync('DELETE FROM cache WHERE owner = ?', owner);
  });
}
