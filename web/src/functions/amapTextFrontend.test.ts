import { describe, expect, it } from 'vitest';
import { amapNormalizeNumbers, amapTextFrontend } from './amapTextFrontend';

describe('AMap text frontend', () => {
  it('matches the APK capture for the approved comparison phrase', () => {
    const clauses = amapTextFrontend('前方200米右转，进入长安街。导航语音测试。');
    expect(clauses.map(clause => Array.from(clause.txtTokens))).toEqual([
      [174, 61, 30, 25, 7, 24, 13, 4, 52, 28, 46, 94, 70, 174],
      [174, 49, 39, 62, 66, 15, 7, 6, 49, 37, 174],
      [174, 16, 10, 27, 7, 84, 39, 14, 17, 64, 162, 174],
    ]);
    expect(Array.from(clauses[0].tone)).toEqual([3, 5, 5, 4, 4, 7, 5, 5, 6, 6, 7, 6, 6, 3]);
    expect(Array.from(clauses[0].prosody)).toEqual([3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 7, 7, 7]);
    expect(Array.from(clauses[0].ph2char)).toEqual([100001, 1, 1, 2, 2, 3, 4, 4, 5, 5, 6, 7, 7, 100001]);
  });

  it('applies third-tone sandhi and basic distance normalization', () => {
    expect(amapNormalizeNumbers('前方200米')).toBe('前方二百米');
    const [hello] = amapTextFrontend('你好');
    expect(Array.from(hello.txtTokens)).toEqual([174, 53, 28, 27, 10, 174]);
    expect(Array.from(hello.tone)).toEqual([3, 5, 5, 6, 6, 3]);
  });

  it('matches separate APK captures for route text and a polyphonic road phrase', () => {
    const [first, second] = amapTextFrontend('前方500米右转，进入人民路。');
    expect(Array.from(first.txtTokens)).toEqual(
      [174, 61, 30, 25, 7, 66, 13, 4, 52, 28, 46, 94, 70, 174]);
    expect(Array.from(first.tone)).toEqual(
      [3, 5, 5, 4, 4, 5, 5, 5, 6, 6, 7, 6, 6, 3]);
    expect(Array.from(second.txtTokens)).toEqual(
      [174, 49, 39, 62, 66, 62, 20, 52, 39, 51, 66, 174]);
    expect(Array.from(amapTextFrontend('请在安全地点掉头')[0].txtTokens)).toEqual(
      [174, 61, 40, 93, 4, 6, 61, 85, 16, 28, 16, 30, 16, 34, 65, 58, 174]);
  });

  it('speaks road codes locally instead of dropping a navigation instruction', () => {
    expect(amapTextFrontend('进入G60沪昆高速')[0].txtTokens.length).toBeGreaterThan(8);
  });

  it('uses the APK neutral-tone ID in ordinary phrases', () => {
    const [clause] = amapTextFrontend('我的车到了。');
    expect(Array.from(clause.txtTokens)).toEqual(
      [174, 81, 16, 17, 15, 17, 16, 10, 51, 17, 174]);
    expect(Array.from(clause.tone)).toEqual([3, 6, 8, 8, 4, 4, 7, 7, 8, 8, 3]);
  });
});
