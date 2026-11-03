/** Local calendar dates as `YYYY-MM-DD` (the API's date format). No time zones: these are wall dates. */

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function parseIsoDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function addDays(d: Date, n: number): Date {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  out.setDate(out.getDate() + n);
  return out;
}

/** The Monday on or after `d` (a run starts on the Monday of its Trial 0 week). */
export function mondayOnOrAfter(d: Date): Date {
  const dow = d.getDay(); // 0 = Sunday
  return addDays(d, (8 - dow) % 7 === 0 && dow === 1 ? 0 : (8 - dow) % 7);
}

/** The next Monday strictly after today, the default start date. */
export function nextMonday(today: Date): Date {
  const dow = today.getDay();
  return addDays(today, dow === 1 ? 7 : (8 - dow) % 7);
}

/** Start-date choices: this week's Monday (if today is Monday) and the next `count` Mondays. */
export function mondayOptions(today: Date, count = 8): Date[] {
  const first = mondayOnOrAfter(today);
  return Array.from({ length: count }, (_, i) => addDays(first, 7 * i));
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Mon Nov 9" */
export function shortDate(d: Date): string {
  return `${DAYS[d.getDay()]} ${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export function dayName(d: Date): string {
  return DAYS[d.getDay()];
}
