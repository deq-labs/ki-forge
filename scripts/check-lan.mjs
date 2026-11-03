// `pnpm check:lan` — checks the PC side of "run the app on my phone over Wi-Fi".
// It can't test from the phone itself, but it catches the usual blockers: the servers aren't running,
// they only listen on localhost, or (Windows) the firewall has no rule for this network profile.
import { execFileSync } from 'node:child_process';
import { platform } from 'node:os';

import { lanAddress } from '../apps/mobile/scripts/lan.mjs';

const ok = (m) => console.log(`  ok    ${m}`);
const bad = (m) => console.log(`  FAIL  ${m}`);
const note = (m) => console.log(`        ${m}`);
let failures = 0;

async function probe(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
    return { status: res.status, body: (await res.text()).slice(0, 80) };
  } catch (e) {
    return { error: e.cause?.code ?? e.message };
  }
}

const lan = lanAddress();
console.log('\nKi Forge LAN check\n');
if (!lan) {
  bad('no private LAN address found (is Wi-Fi connected?)');
  process.exit(1);
}
ok(`this PC is ${lan.ip} on "${lan.name}" — the phone must be on the same network (its IP should start with ${lan.ip.split('.').slice(0, 3).join('.')}.)`);

for (const [name, path, fix] of [
  ['Expo dev server', `http://${lan.ip}:8081/status`, 'cd apps/mobile && pnpm start'],
  ['API', `http://${lan.ip}:8000/healthz`, 'docker compose --profile full up -d'],
]) {
  const r = await probe(path);
  if (r.status === 200) ok(`${name} answers at ${path}`);
  else {
    failures++;
    bad(`${name} not reachable at ${path} (${r.error ?? `HTTP ${r.status}`})`);
    note(`start it: ${fix}`);
  }
}

if (platform() === 'win32') {
  const ps = (cmd) =>
    execFileSync('powershell', ['-NoProfile', '-Command', cmd], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  try {
    const category = ps(`(Get-NetConnectionProfile -InterfaceAlias '${lan.name}').NetworkCategory`);
    ok(`Windows network profile for "${lan.name}": ${category}`);
    const rules = ps(
      `Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow | Where-Object { $_.DisplayName -like 'Ki Forge*' } | ForEach-Object { $_.Profile.ToString() }`,
    );
    const covered = rules.split(/\r?\n/).some((p) => p.includes(category) || p.includes('Any'));
    if (covered) ok(`firewall rule "Ki Forge dev" allows 8081/8000 on ${category} networks`);
    else {
      failures++;
      bad(`no "Ki Forge dev" firewall rule for ${category} networks — the phone's requests are dropped`);
      note('In Terminal (Admin):');
      note(
        `New-NetFirewallRule -DisplayName "Ki Forge dev (Expo 8081, API 8000)" -Direction Inbound -Protocol TCP -LocalPort 8081,8000 -RemoteAddress LocalSubnet -Action Allow -Profile ${category}`,
      );
    }
  } catch {
    note('could not read Windows firewall settings (skipped)');
  }
}

console.log(
  failures
    ? `\n${failures} problem(s). Fix them, then open http://${lan.ip}:8081/status in the phone's browser.\n`
    : `\nThe PC side looks right. If the phone still can't open http://${lan.ip}:8081/status, the router is\nkeeping devices apart (guest network, "AP/client isolation", or a different band/VLAN).\n`,
);
process.exit(failures ? 1 : 0);
