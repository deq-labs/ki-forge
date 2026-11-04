/**
 * Turn a sync response into what the rewards UI shows. No XP math here: every number comes from the
 * server's awards (`xp_awarded`) and its per-session totals (`sessions[].xp`).
 */

export type Award = { type: string; amount: number; source_id: string };
export type SessionOutcome = { client_id: string; cleared: boolean; all_on_target: boolean; xp: number };
export type Reward = {
  xp_awarded: Award[];
  sessions: SessionOutcome[];
  level_up: { from: number; to: number; rank: string } | null;
  new_badges: { slug: string; name: string; description: string; xp_reward: number }[];
};

export type Line = { label: string; xp: number };
export type Breakdown = { lines: Line[]; total: number; questCleared: boolean };

/** Kind of moment: a level up (full overlay), a cleared quest (sheet), a badge only (toast), or nothing. */
export function momentOf(r: Reward): 'level_up' | 'quest' | 'badge' | null {
  if (r.level_up) return 'level_up';
  if (r.xp_awarded.some((a) => ['session_cleared', 'full_week', 'trial_completed'].includes(a.type))) return 'quest';
  if (r.new_badges.length) return 'badge';
  return null;
}

/** The quest-cleared card: sets logged, session cleared, every set on target, full week. */
export function breakdown(r: Reward): Breakdown {
  const cleared = r.xp_awarded.filter((a) => a.type === 'session_cleared');
  const lines: Line[] = [];
  for (const c of cleared) {
    const session = r.sessions.find((s) => s.client_id === c.source_id);
    const bonus = r.xp_awarded
      .filter((a) => a.source_id === c.source_id && (a.type === 'session_cleared' || a.type === 'all_on_target'))
      .reduce((n, a) => n + a.amount, 0);
    const setsXp = session ? session.xp - bonus : 0;
    if (setsXp > 0) lines.push({ label: `${setsXp / 5} sets logged`, xp: setsXp });
    lines.push({ label: 'Session cleared', xp: c.amount });
    const onTarget = r.xp_awarded.find((a) => a.source_id === c.source_id && a.type === 'all_on_target');
    if (onTarget) lines.push({ label: 'Every set on target', xp: onTarget.amount });
  }
  if (!cleared.length) {
    const sets = r.xp_awarded.filter((a) => a.type === 'set_logged').reduce((n, a) => n + a.amount, 0);
    if (sets) lines.push({ label: `${sets / 5} sets logged`, xp: sets });
  }
  const week = r.xp_awarded.filter((a) => a.type === 'full_week').reduce((n, a) => n + a.amount, 0);
  if (week) lines.push({ label: 'Full week bonus', xp: week });
  const trial = r.xp_awarded.filter((a) => a.type === 'trial_completed').reduce((n, a) => n + a.amount, 0);
  if (trial) lines.push({ label: 'Trial complete', xp: trial });
  return { lines, total: lines.reduce((n, l) => n + l.xp, 0), questCleared: cleared.length > 0 };
}

/** "Two levels to Warrior rank." for the level-up copy; null at the top rank. */
export function nextRankLine(level: number, ranks: { from_level: number; name: string }[]): string | null {
  const next = [...ranks].sort((a, b) => a.from_level - b.from_level).find((r) => r.from_level > level);
  if (!next) return null;
  const n = next.from_level - level;
  const words = ['', 'One level', 'Two levels', 'Three levels', 'Four levels'];
  return `${words[n] ?? `${n} levels`} to ${next.name} rank.`;
}
