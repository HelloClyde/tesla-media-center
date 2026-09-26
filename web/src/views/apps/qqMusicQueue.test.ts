// @vitest-environment node
import { expect, it } from 'vitest';
import { nextIndex } from './qqMusicQueue';
it('handles ends, empty lists and single-track loops', () => {
 expect(nextIndex(0, 0, 1, 'loop')).toBe(-1);
 expect(nextIndex(3, 2, 1, 'order')).toBe(-1);
 expect(nextIndex(3, 2, 1, 'loop')).toBe(0);
 expect(nextIndex(3, 0, -1, 'loop')).toBe(2);
 expect(nextIndex(3, 1, 1, 'single', true)).toBe(1);
 expect(nextIndex(3, 1, 1, 'single')).toBe(2);
 expect(nextIndex(1, 0, 1, 'shuffle', true)).toBe(0);
});
it('shuffle chooses another track without an out-of-range index', () => {
 expect(nextIndex(3, 1, 1, 'shuffle', false, () => 0)).toBe(2);
 expect(nextIndex(3, 1, 1, 'shuffle', false, () => .999)).toBe(0);
});
