// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { parseLrc, parseQrc, lyricIndex } from './qqMusicLyrics';
describe('synchronized lyrics', () => {
  it('supports repeated timestamps, fractions, metadata and offsets', () => {
    expect(parseLrc('[ar:artist]\n[offset:-200]\n[00:02.50][00:04.125]Hello\n[00:01]First')).toEqual([
      { time: .8, text: 'First' }, { time: 2.3, text: 'Hello' }, { time: 3.925, text: 'Hello' }
    ]);
  });
  it('tracks forward and backward seeking, intro and end', () => {
    const lines = parseLrc('[00:02]A\n[00:05]B');
    expect([0, 2, 8, 3].map(time => lyricIndex(lines, time))).toEqual([-1, 0, 1, 0]);
    expect(lyricIndex([], 20)).toBe(-1);
    expect(parseLrc('纯音乐')).toEqual([]);
  });
});

it('parses QRC word timing and ignores non-QRC fallback', () => {
 expect(parseQrc('[1000,1000]你(1000,300)好(1300,700)')[0]).toEqual({time:1,text:'你好',words:[{text:'你',time:1,duration:.3},{text:'好',time:1.3,duration:.7}]});
 expect(parseQrc('[00:01]你好')).toEqual([]);
});
