import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { isoDate, mondayOnOrAfter, mondayOptions, nextMonday, parseIsoDate, shortDate } from './dates.ts';

const d = (s: string) => parseIsoDate(s);

describe('start dates', () => {
  it('round-trips ISO dates', () => assert.equal(isoDate(d('2026-11-09')), '2026-11-09'));

  it('next Monday is strictly after today', () => {
    assert.equal(isoDate(nextMonday(d('2026-11-03'))), '2026-11-09'); // Tue
    assert.equal(isoDate(nextMonday(d('2026-11-08'))), '2026-11-09'); // Sun
    assert.equal(isoDate(nextMonday(d('2026-11-09'))), '2026-11-16'); // Mon
  });

  it('Monday on or after keeps a Monday', () => {
    assert.equal(isoDate(mondayOnOrAfter(d('2026-11-09'))), '2026-11-09');
    assert.equal(isoDate(mondayOnOrAfter(d('2026-11-10'))), '2026-11-16');
  });

  it('options are consecutive Mondays only', () => {
    const opts = mondayOptions(d('2026-11-03'), 4);
    assert.deepEqual(opts.map(isoDate), ['2026-11-09', '2026-11-16', '2026-11-23', '2026-11-30']);
    assert.ok(opts.every((o) => o.getDay() === 1));
  });

  it('crosses month and year ends', () => {
    assert.deepEqual(mondayOptions(d('2026-12-29'), 2).map(isoDate), ['2027-01-04', '2027-01-11']);
  });

  it('formats short dates', () => assert.equal(shortDate(d('2026-11-09')), 'Mon Nov 9'));
});
