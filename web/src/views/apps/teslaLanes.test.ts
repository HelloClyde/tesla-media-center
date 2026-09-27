import { describe, it, expect } from 'vitest';
import { createLaneMesh } from './teslaLanes';

describe('real lane boundary ground layer', () => {
  it('clips crossing lines, deduplicates reversed boundaries and ignores source height', () => {
    const mesh = createLaneMesh([[[115.99,40,99999],[116.01,40,-99999]],[[116.01,40,0],[115.99,40,0]]], [116,40]);
    expect(mesh?.userData.segmentCount).toBe(1);
    const position = mesh!.geometry.getAttribute('position');
    for(let i=0;i<position.count;i++) {
      expect(Math.abs(position.getX(i))).toBeLessThanOrEqual(300.1);
      expect(position.getY(i)).toBeCloseTo(.04);
    }
    mesh!.geometry.dispose(); mesh!.material.dispose();
  });
  it('does not render empty, distant, invalid or degenerate segments', () => {
    expect(createLaneMesh([[],[[117,40],[118,40]],[[116,40],[116,40]],[[NaN,40],[116,40]]],[116,40])).toBeUndefined();
  });
});
