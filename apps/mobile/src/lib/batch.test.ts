import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { chunkBatch, orderEdits } from './batch.ts';
import { uuid4 } from './uuid.ts';

const set = (id: string, supersedes: string | null = null) => ({ client_id: id, supersedes_client_id: supersedes });

describe('sync batches', () => {
  it('puts every session in the first request and caps each request', () => {
    const sets = Array.from({ length: 1_050 }, (_, i) => set(`s${i}`));
    const batches = chunkBatch(['a', 'b'], sets, 500);
    assert.deepEqual(
      batches.map((b) => [b.sessions.length, b.sets.length]),
      [
        [2, 500],
        [0, 500],
        [0, 50],
      ],
    );
  });

  it('sends a sessions-only request (e.g. a completion time)', () => {
    assert.deepEqual(chunkBatch(['a'], []), [{ sessions: ['a'], sets: [] }]);
    assert.deepEqual(chunkBatch([], []), []);
  });

  it('orders edits after what they supersede', () => {
    const ordered = orderEdits([set('e2', 'e1'), set('e1', 'a'), set('a'), set('b', 'already-synced')]);
    const pos = (id: string) => ordered.findIndex((s) => s.client_id === id);
    assert.ok(pos('a') < pos('e1') && pos('e1') < pos('e2'));
    assert.equal(ordered.length, 4);
  });

  it('keeps cycles instead of looping forever', () => {
    assert.equal(orderEdits([set('x', 'y'), set('y', 'x')]).length, 2);
  });
});

describe('uuid4', () => {
  it('is a version 4 UUID and unique', () => {
    const ids = new Set(Array.from({ length: 1_000 }, uuid4));
    assert.equal(ids.size, 1_000);
    for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
});
