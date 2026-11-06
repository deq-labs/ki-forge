import assert from 'node:assert/strict';
import { test } from 'node:test';

import { formatLoad, fromLb, liftInput, parseLift } from './lifts.ts';

test('parses 1RMs in lb and kg', () => {
  assert.equal(parseLift('305', 'imperial'), 305);
  assert.equal(parseLift(' 102,5 ', 'imperial'), 102.5);
  assert.equal(parseLift('140', 'metric'), 308.6); // 140 kg → 308.6 lb
  assert.equal(parseLift('', 'imperial'), null);
  assert.equal(parseLift('0', 'imperial'), 'invalid');
  assert.equal(parseLift('abc', 'imperial'), 'invalid');
  assert.equal(parseLift('2500', 'imperial'), 'invalid');
});

test('round-trips a kg entry through lb', () => {
  const lb = parseLift('140', 'metric') as number;
  assert.equal(fromLb(lb, 'metric'), 140);
  assert.equal(liftInput(fromLb(225, 'metric')), '102');
  assert.equal(liftInput(102.5), '102.5');
});

test('formats loads', () => {
  assert.equal(formatLoad(245, 'imperial'), '245 lb');
  assert.equal(formatLoad(245, 'metric'), '111 kg');
});
