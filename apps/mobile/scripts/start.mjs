// `pnpm start` = `expo start`, but with the PC's real LAN IP in the QR code.
// Docker Desktop / WSL / Hyper-V add virtual adapters (e.g. "vEthernet (WSL)") that Expo
// sometimes picks; a phone on Wi-Fi can't reach those. Override with REACT_NATIVE_PACKAGER_HOSTNAME.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { networkInterfaces } from 'node:os';

const VIRTUAL = /vEthernet|WSL|Hyper-V|Docker|VirtualBox|VMware|Loopback|Bluetooth|Tailscale|ZeroTier/i;
const isPrivate = (ip) => /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(ip);

export function lanAddress() {
  const candidates = [];
  for (const [name, addrs] of Object.entries(networkInterfaces())) {
    if (VIRTUAL.test(name)) continue;
    for (const a of addrs ?? []) {
      if (a.family === 'IPv4' && !a.internal && isPrivate(a.address)) candidates.push({ name, ip: a.address });
    }
  }
  // Prefer Wi-Fi / Ethernet by name, then anything else private.
  candidates.sort((a, b) => Number(/wi-?fi|wlan|ethernet|en\d/i.test(b.name)) - Number(/wi-?fi|wlan|ethernet|en\d/i.test(a.name)));
  return candidates[0];
}

const env = { ...process.env };
if (!env.REACT_NATIVE_PACKAGER_HOSTNAME) {
  const lan = lanAddress();
  if (lan) {
    env.REACT_NATIVE_PACKAGER_HOSTNAME = lan.ip;
    console.log(`Using ${lan.ip} (${lan.name}) for the QR code. Set REACT_NATIVE_PACKAGER_HOSTNAME to override.`);
  } else {
    console.warn('No LAN address found; letting Expo choose.');
  }
}

const require = createRequire(import.meta.url);
const cli = require.resolve('expo/bin/cli');
const child = spawn(process.execPath, [cli, 'start', ...process.argv.slice(2)], { stdio: 'inherit', env });
child.on('exit', (code) => process.exit(code ?? 0));
