import { describe, expect, it } from 'vitest';
import { formatRouteDuration, formatRouteTolls } from './amapRouteSummary';

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
