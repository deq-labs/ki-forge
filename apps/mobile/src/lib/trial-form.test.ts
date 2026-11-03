import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { ALL_TESTS, formatField, formatRow, parseField, parseNumber, parseRow } from './trial-form.ts';

describe('trial form', () => {
  it('covers the 9 tests once each', () => {
    assert.equal(ALL_TESTS.length, 9);
    assert.equal(new Set(ALL_TESTS).size, 9);
  });

  it('parses the row as mm:ss or seconds', () => {
    assert.equal(parseRow('8:30'), 510);
    assert.equal(parseRow('10:00'), 600);
    assert.equal(parseRow('510'), 510);
    assert.equal(parseRow(''), null);
    assert.equal(parseRow('8:75'), undefined);
    assert.equal(parseRow('abc'), undefined);
    assert.equal(formatRow(510), '8:30');
    assert.equal(formatRow(600), '10:00');
  });

  it('parses plain numbers', () => {
    assert.equal(parseNumber('45.5'), 45.5);
    assert.equal(parseNumber('45,5'), 45.5);
    assert.equal(parseNumber('8'), 8);
    assert.equal(parseNumber(' '), null);
    assert.equal(parseNumber('-3'), undefined);
    assert.equal(parseNumber('1e3'), undefined);
  });

  it('round-trips through the field helpers', () => {
    assert.equal(formatField('row_2k_seconds', parseField('row_2k_seconds', '9:05')), '9:05');
    assert.equal(formatField('waist_in', parseField('waist_in', '34')), '34');
    assert.equal(formatField('waist_in', null), '');
  });
});
