/**
 * Split unsynced rows into sync requests. Every session goes in the first request so later requests'
 * sets always reference a session the server already has; edits stay after the sets they supersede.
 */
export const MAX_BATCH = 500; // the API's per-request cap (services/api/app/api/sync.py)

export function chunkBatch<S, T extends { client_id: string; supersedes_client_id: string | null }>(
  sessions: S[],
  sets: T[],
  max = MAX_BATCH,
): { sessions: S[]; sets: T[] }[] {
  if (sessions.length > max) throw new RangeError(`more than ${max} unsynced sessions`);
  const ordered = orderEdits(sets);
  const out: { sessions: S[]; sets: T[] }[] = [];
  for (let i = 0; i < Math.max(ordered.length, 1); i += max) {
    out.push({ sessions: i === 0 ? sessions : [], sets: ordered.slice(i, i + max) });
  }
  return out.filter((b) => b.sessions.length || b.sets.length);
}

/** Stable order in which every edit comes after the row it supersedes (when both are pending). */
export function orderEdits<T extends { client_id: string; supersedes_client_id: string | null }>(sets: T[]): T[] {
  const ids = new Set(sets.map((s) => s.client_id));
  const placed = new Set<string>();
  const out: T[] = [];
  let remaining = [...sets];
  while (remaining.length) {
    const next = remaining.filter(
      (s) => !s.supersedes_client_id || !ids.has(s.supersedes_client_id) || placed.has(s.supersedes_client_id),
    );
    if (!next.length) return [...out, ...remaining]; // a cycle: let the server reject it
    for (const s of next) {
      out.push(s);
      placed.add(s.client_id);
    }
    remaining = remaining.filter((s) => !placed.has(s.client_id));
  }
  return out;
}
