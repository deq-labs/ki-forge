// free-exercise-db -> db/seed/exercise_library.json
// Run with `pnpm import:library [commit]`. The dataset is public domain (Unlicense):
// https://github.com/yuhonas/free-exercise-db. Pinning a commit keeps the data and the image URLs stable;
// images are not copied into the repo (the API builds their URLs from EXERCISE_IMAGES_BASE_URL).
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = 'yuhonas/free-exercise-db';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const out = resolve(root, 'db/seed/exercise_library.json');

async function json(url) {
  const r = await fetch(url, { headers: { 'User-Agent': 'ki-forge-import' } });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

const commit = process.argv[2] ?? (await json(`https://api.github.com/repos/${REPO}/commits/main`)).sha;
const raw = await json(`https://raw.githubusercontent.com/${REPO}/${commit}/dist/exercises.json`);

const exercises = raw
  .map((e) => ({
    id: e.id,
    name: e.name.trim(),
    category: e.category,
    equipment: e.equipment ?? null,
    level: e.level,
    force: e.force ?? null,
    mechanic: e.mechanic ?? null,
    primary_muscles: e.primaryMuscles ?? [],
    secondary_muscles: e.secondaryMuscles ?? [],
    instructions: (e.instructions ?? []).map((s) => s.trim()).filter(Boolean),
    images: e.images ?? [],
  }))
  .sort((a, b) => a.id.localeCompare(b.id));

const ids = new Set();
for (const e of exercises) {
  if (ids.has(e.id)) throw new Error(`duplicate id ${e.id}`);
  ids.add(e.id);
}

const data = {
  source: `https://github.com/${REPO}`,
  commit,
  license: 'Unlicense (public domain)',
  exercises,
};
writeFileSync(out, JSON.stringify(data, null, 1) + '\n');
console.log(`wrote ${exercises.length} exercises from ${REPO}@${commit.slice(0, 7)} to db/seed/exercise_library.json`);
