import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { gaugePercent, scanAdvice } from './scan.ts';

describe('scan gauge and advice', () => {
  it('places ratios on the 1.20–1.80 gauge', () => {
    assert.equal(gaugePercent(1.2), 0);
    assert.equal(gaugePercent(1.5), 50);
    assert.equal(gaugePercent(1.8), 100);
    assert.equal(gaugePercent(1.0), 0); // clamped
    assert.equal(gaugePercent(2.1), 100);
  });

  it('says how far to go (the mockup: 1.34 vs 1.60 at a 34" waist)', () => {
    assert.equal(
      scanAdvice(1.34, 1.6, 34),
      '0.26 to go. Adding 1" to your shoulders or losing 1" from your waist moves you about 0.03.',
    );
    assert.equal(scanAdvice(1.34, 1.6, null), '0.26 to go.');
    assert.match(scanAdvice(1.62, 1.6, 30), /^Target reached/);
    assert.match(scanAdvice(null, 1.6, null), /^Log your shoulders/);
  });
});
