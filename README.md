# Ki Forge Fitness: Claude Code starter kit

Everything Claude Code needs to build the app: rules for the agent, specs, schema, seed data, design tokens, screen mockups, a working prototype, and the spreadsheet fixture for testing.

## Start here

1. Install Claude Code if needed, open a terminal in this folder and run `claude`.
2. Copy your filled spreadsheet into `fixtures/` as `joe_training_log.xlsx`. Open and save it once in Excel or Google Sheets first so its calculated values are stored.
3. Move the two files in `_setup/claude-commands/` into `.claude/commands/` (creates the `/milestone` and `/parity` slash commands).
4. Paste the **Session 1** prompt from `docs/00-kickoff-prompt.md`.

Prerequisites on your PC: Node 26 LTS, pnpm 12 (`npm i -g pnpm`), Docker Desktop (Postgres 18, and all Python: the API runs in a Python 3.15 container), Git, and the Expo Go app or an EAS dev build on your phone. See the Commands section of `CLAUDE.md`.

## Run it locally

Run everything from the repo root in a normal terminal. Docker Desktop must be running.

**First time only**

```
pnpm install
docker compose up -d db
docker compose build api
docker compose run --rm api uv run alembic upgrade head
```

**The app in a browser**

```
cd apps/mobile
pnpm web
```

A browser tab opens. Press `Ctrl+C` to stop.

**The app on your phone**

1. Install **Expo Go** from the App Store or Play Store.
2. Make sure the phone and PC are on the same Wi-Fi.
3. Run `cd apps/mobile` then `pnpm start`.
4. Scan the QR code in the terminal (iPhone: Camera app; Android: inside Expo Go). Don't press `s`: that switches the QR code to development-build mode, which Expo Go can't open.

`pnpm start` puts your PC's Wi-Fi IP in the QR code. Plain `npx expo start` can pick Docker's virtual adapter (e.g. `192.168.16.1`), which the phone can't reach. To force an address, set `REACT_NATIVE_PACKAGER_HOSTNAME` first.

If the phone still can't connect, Windows Firewall is usually blocking Node. Allow it on private networks, or run `pnpm start --tunnel`.

**The API** (not used by the app until M2–M3)

```
docker compose --profile full up -d     # API on http://localhost:8000, plus the worker
docker compose --profile full down      # stop it
```

**Tests and checks**

```
docker compose run --rm api uv run pytest
pnpm -w lint
pnpm -w typecheck
```

**Day to day:** start Docker Desktop, run `docker compose up -d db`, then `pnpm start` from `apps/mobile`.

## Workflow

Every change starts from an issue (grouped by milestone).

1. Branch from an up-to-date `main` as `<issue#>-<short-slug>`, e.g. `3-program-model-calendar`.
2. Open a PR into `main`; the template asks for `Closes #N`, so merging closes the issue.
3. Merge when CI is green, then `git checkout main && git pull`.

## What's here

| Path | What |
| --- | --- |
| `db/0001_initial.sql` | Postgres 16 schema, tested |
| `db/seed/program.json` | All program content: 52 exercises, 6 session templates, 11 phases, 4 paths, tests, badges, ranks |
| `db/load_seed.py` | Reference loader (tested against the schema) |
| `design/tokens.json` | Colors, type, spacing, radii, shadows |
| `design/screens/*.png` | 7 mockups at 390 × 844 (fallback fonts in the renders) |
| `design/reference/prototype.html` | Clickable single-file prototype; open in a browser |
| `design/reference/components.css` | Web CSS for the design system components |
| `fixtures/Ki_Forge_Training_Log_TEMPLATE.xlsx` | Empty workbook, for the importer's zero case |

## Live versions

- Architecture doc with diagrams: https://claude.ai/artifact/KYduJQZ6FJCsbarcity3aL
- Design system: https://claude.ai/artifact/TZDgMowuxZr93pmJUcHMjU
- App screens canvas: https://claude.ai/artifact/JbTHW27tAgtNFyU3unE7BN
- Training program: https://claude.ai/artifact/SioEsFP66oorjLXwTDxWzC

## Decisions already made

- XP and level math match the spreadsheet exactly (v1). Extra rules from the original program (PR bonus, protein, deload, side quests) are v1.1, behind flags.
- Ranks are Rookie → Fighter → Warrior → Elite → Ascended → Ascended II → Mythic. The original program's franchise-named ranks are not used anywhere.
- The personal trial runs at $0: API and Postgres on your PC, app on your phone over Wi-Fi. Cloud, auth and payments come in M6.
