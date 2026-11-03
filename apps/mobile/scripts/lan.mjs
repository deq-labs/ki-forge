// The PC's real LAN address (skips Docker / WSL / Hyper-V / VPN virtual adapters a phone can't reach).
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
