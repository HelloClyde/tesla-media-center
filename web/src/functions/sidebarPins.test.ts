import { expect, it } from 'vitest';
import { placeSidebarApp } from './sidebarPins';
const full = ['a','b','c','d','e','f','g'];
it('replaces the targeted slot when full', () => {
  expect(placeSidebarApp(full,'h','c')).toEqual(['a','b','h','d','e','f','g']);
  expect(placeSidebarApp(full,'h')).toEqual(['a','b','c','d','e','f','h']);
});
it('reorders pinned apps without ejecting another one', () => {
  expect(placeSidebarApp(full,'g','b')).toEqual(['a','g','b','c','d','e','f']);
});
it('inserts into an available slot', () => {
  expect(placeSidebarApp(['a','b'],'c','b')).toEqual(['a','c','b']);
});
