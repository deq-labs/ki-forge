import * as SQLite from 'expo-sqlite';

/**
 * The on-device database (CLAUDE.md rule 3: a set is written here before any network call).
 * Every row carries `owner` (the signed-in identity) so switching dev users never mixes data.
 * Migrations are append-only, tracked with PRAGMA user_version.
 */
const MIGRATIONS: string[] = [
  // 1: sessions, sets (append-only edits), sync flags, cached API responses
  `
  CREATE TABLE sessions (
    client_id     TEXT PRIMARY KEY NOT NULL,
    owner         TEXT NOT NULL,
    template_code TEXT NOT NULL,
    week          INTEGER NOT NULL,
    garage_mode   INTEGER NOT NULL DEFAULT 0,
    started_at    TEXT NOT NULL,
    completed_at  TEXT,
    synced        INTEGER NOT NULL DEFAULT 0
  );
  CREATE INDEX sessions_owner_week ON sessions(owner, week, template_code);

  CREATE TABLE sets (
    client_id            TEXT PRIMARY KEY NOT NULL,
    owner                TEXT NOT NULL,
    session_client_id    TEXT NOT NULL REFERENCES sessions(client_id),
    exercise_slug        TEXT NOT NULL,
    set_no               INTEGER NOT NULL,
    weight_lb            REAL NOT NULL DEFAULT 0,
    reps                 INTEGER,
    rir                  INTEGER,
    is_swap              INTEGER NOT NULL DEFAULT 0,
    supersedes_client_id TEXT,
    logged_at            TEXT NOT NULL,
    synced               INTEGER NOT NULL DEFAULT 0
  );
  CREATE INDEX sets_session ON sets(session_client_id);
  CREATE INDEX sets_unsynced ON sets(owner, synced);

  CREATE TABLE cache (
    owner      TEXT NOT NULL,
    key        TEXT NOT NULL,
    json       TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (owner, key)
  );
  `,
];

export async function migrate(db: SQLite.SQLiteDatabase): Promise<void> {
  await db.execAsync('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
  const row = await db.getFirstAsync<{ user_version: number }>('PRAGMA user_version');
  let version = row?.user_version ?? 0;
  while (version < MIGRATIONS.length) {
    const sql = MIGRATIONS[version];
    await db.withTransactionAsync(async () => {
      await db.execAsync(sql);
      await db.execAsync(`PRAGMA user_version = ${version + 1}`);
    });
    version += 1;
  }
}

let opening: Promise<SQLite.SQLiteDatabase> | null = null;

/** The app's database, opened and migrated once. */
export function getDb(): Promise<SQLite.SQLiteDatabase> {
  if (!opening) {
    opening = (async () => {
      const db = await SQLite.openDatabaseAsync('kiforge.db');
      await migrate(db);
      return db;
    })();
    opening.catch(() => {
      opening = null; // let the next call retry
    });
  }
  return opening;
}
