import { describe, expect, it } from 'vitest';
import { layoutPlaceLabels, type PlaceLabel } from './amapPlaceLabels';
const label = (name: string, x: number, y: number, priority = 2): PlaceLabel => ({
  name, point: [x,y], minZoom: 4, maxZoom: 5, kind: 'city', priority,
});
const project = ([x,y]: [number, number]) => ({x,y});
describe('province and city label layout', () => {
  it('deduplicates tiles, respects zoom and clips viewport', () => {
    const labels = [label('北京',100,100),label('北京',100,100),label('广州',250,200),label('屏外',-10,100)];
    expect(layoutPlaceLabels(labels,4,400,300,project).map(l=>l.name)).toEqual(['北京','广州']);
    expect(layoutPlaceLabels(labels,6,400,300,project)).toEqual([]);
  });
  it('prioritizes the capital and prevents adjacent text rectangles colliding', () => {
    const labels = [label('普通城市',110,100),label('北京',100,100,0),label('远处城市',250,100)];
    expect(layoutPlaceLabels(labels,4,400,300,project).map(l=>l.name)).toEqual(['北京','远处城市']);
  });
});
