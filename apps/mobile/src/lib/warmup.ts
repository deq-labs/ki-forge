/**
 * Turn a warm-up line from the program into checklist steps:
 * "3 rounds: 10 RDLs, 5 kip swings, 250 m row. Then 2–3 ramp sets on the main lift (bar → 50% → 70%)."
 * → detail "10 RDLs, 5 kip swings, 250 m row", steps ["Round 1", "Round 2", "Round 3", "Ramp sets"].
 */
export function warmupSteps(text: string): { detail: string; steps: string[] } {
  const m = /^\s*(\d+)\s+rounds?\s*:\s*(.*)$/i.exec(text);
  const rounds = m ? Math.min(10, Number(m[1])) : 0;
  let rest = m ? m[2] : text;
  const ramp = /\bramp sets?\b/i.test(rest);
  const then = rest.search(/\s*Then\b/);
  if (then >= 0) rest = rest.slice(0, then);
  const detail = rest.trim().replace(/\.$/, '');
  const steps = rounds ? Array.from({ length: rounds }, (_, i) => `Round ${i + 1}`) : ['Done'];
  if (ramp) steps.push('Ramp sets');
  return { detail, steps };
}
