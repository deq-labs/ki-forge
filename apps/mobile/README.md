# @kiforge/mobile

Expo (SDK 58) app for iOS, Android and web. Routes live in `src/app/` (Expo Router).

- `src/theme/tokens.ts` is generated: run `pnpm gen:tokens` at the repo root.
- `pnpm test` runs the app's logic tests (Node's built-in runner; `xp.ts` mirrors the Python golden values).

See the repo root `CLAUDE.md` and `docs/` for specs.

## Run it on your phone (personal trial, $0)

The API and Postgres run on your PC; the phone loads the app from the Expo dev server on the same PC.

1. **Start the API** (repo root): `docker compose --profile full up -d` — API on port 8000, plus the worker.
2. **Start the app**: `cd apps/mobile && pnpm start` — the QR code uses the PC's real Wi-Fi address (it skips
   Docker/WSL adapters). Add `--clear` after changing `metro.config.js` or packages.
3. **Check the PC side**: `pnpm check:lan` (repo root). It confirms both servers answer on the LAN address and,
   on Windows, that the firewall lets them through for the current network profile (Public or Private).
4. On the phone: open `http://<PC IP>:8081/status` in the browser — it should say `packager-status:running`.
   Then scan the QR code with **Expo Go** (not an entry under "Recently opened"), sign in with an email, and
   onboard. The app finds the API at the same address on port 8000; Profile › Server overrides it.

**If the phone can't open the status page** but `pnpm check:lan` is all ok, the network is keeping devices
apart: a guest network, router "AP/client isolation", or the phone on another band/VLAN of a mesh router. Check
that the phone's IP starts with the same three numbers as the PC's.

**Windows firewall** (once, in Terminal (Admin)) — allows only devices on your local network:

```powershell
New-NetFirewallRule -DisplayName "Ki Forge dev (Expo 8081, API 8000)" -Direction Inbound -Protocol TCP `
  -LocalPort 8081,8000 -RemoteAddress LocalSubnet -Action Allow -Profile Public
```

Use `-Profile Private` instead if your Wi-Fi is set to Private. Until real sign-in (M6) the API trusts the email
the app sends, so don't leave it running on public Wi-Fi.

**Web**: `pnpm web` (same API). The dev server sends COOP/COEP headers so on-device SQLite works in the browser.

## M3 acceptance (docs/07-build-plan.md)

- [ ] Airplane mode: log a full Upper A (week 1). Network back on: sync completes, XP rises by **240**
      (115 for 23 sets + 100 cleared + 25 all on target; +75 more the first time for the First Blood badge).
- [ ] Kill the app mid-session and relaunch: logged sets are still there (they live in SQLite).
- [ ] Web build loads (`pnpm web`).
- [ ] Screens match `design/screens/*.png` in layout and tokens (Base, Train, path picker, level up).
