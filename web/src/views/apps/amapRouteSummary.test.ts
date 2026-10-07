import { describe, expect, it } from 'vitest';
import { formatRemainingDuration, formatRouteDuration, formatRouteTolls, remainingRouteDuration } from './amapRouteSummary';
import { cumulative, type AppRoute } from './amapNavigation';

describe('route comparison summary', () => {
  it('formats seconds without losing the hour boundary', () => {
    expect(formatRouteDuration(8460)).toBe('约 2 小时 21 分钟');
    expect(formatRouteDuration(3600)).toBe('约 1 小时');
    expect(formatRouteDuration(61)).toBe('约 2 分钟');
    expect(formatRouteDuration(null)).toBe('用时待确认');
    expect(formatRouteDuration(NaN)).toBe('用时待确认');
  });
  it('distinguishes unknown tolls from zero and displays decimals', () => {
    expect(formatRouteTolls({})).toBe('收费待确认');
    expect(formatRouteTolls({ tolls: 0, tollCurrency: 'CNY' })).toBe('不收费');
    expect(formatRouteTolls({ tolls: 71.5, tollCurrency: 'CNY' })).toBe('预计收费 ¥71.5');
    expect(formatRouteTolls({ tolls: 71, tollCurrency: 'USD' })).toBe('收费待确认');
  });
});

describe('remaining navigation time', () => {
  const route: AppRoute = { id: 0, path: [[120, 30], [120, 30.01], [120, 30.02]],
    steps: [], breaks: [], distance: 2200, labels: [], duration: 1800 };
  const lengths = cumulative(route), total = lengths[lengths.length - 1];

  it('keeps planned driving time at the start and updates it with measured progress', () => {
    expect(remainingRouteDuration(route, 0)).toBe(1800);
    expect(remainingRouteDuration(route, total / 2)).toBeCloseTo(900);
    expect(formatRemainingDuration(remainingRouteDuration(route, total / 2))).toBe('约 15 分钟');
    // Reporting-distance rounding must not change the geometric progress ratio.
    expect(remainingRouteDuration({ ...route, distance: 2400 }, total / 2)).toBeCloseTo(900);
  });

  it('clamps progress at either end and handles the last minute', () => {
    expect(remainingRouteDuration(route, -20)).toBe(1800);
    expect(remainingRouteDuration(route, total + 20)).toBe(0);
    expect(formatRemainingDuration(0)).toBe('不足 1 分钟');
    expect(formatRemainingDuration(59)).toBe('不足 1 分钟');
    expect(formatRemainingDuration(60)).toBe('约 1 分钟');
    expect(formatRemainingDuration(3600)).toBe('约 1 小时');
  });

  it('reports unknown time for missing estimates and unusable geometry', () => {
    for (const duration of [undefined, null, 0, -1, NaN, Infinity]) {
      expect(remainingRouteDuration({ ...route, duration }, 0)).toBeNull();
    }
    expect(remainingRouteDuration(route, NaN)).toBeNull();
    expect(remainingRouteDuration({ ...route, path: [] }, 0)).toBeNull();
    expect(remainingRouteDuration({ ...route, path: [[120, 30], [120, 30]] }, 0)).toBeNull();
    expect(formatRemainingDuration(null)).toBe('时间待确认');
    expect(formatRemainingDuration(NaN)).toBe('时间待确认');
  });

  it('resets to a new route estimate after replanning instead of retaining old time', () => {
    expect(remainingRouteDuration(route, total / 2)).toBeCloseTo(900);
    expect(remainingRouteDuration({ ...route, duration: 2400 }, 0)).toBe(2400);
  });
});
