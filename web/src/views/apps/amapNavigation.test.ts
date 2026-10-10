import { describe, expect, it } from 'vitest';
import { cumulative, instruction, upcomingInstructions, matchPosition, pointAt, type AppRoute } from './amapNavigation';
import {navigationArrowAsset, type NavigationManeuver} from '@/components/navigationArrow';
import {navigationVoicePhrase} from './amapVoicePhrases';
const route: AppRoute = { id: 0, path: [[116, 39], [116, 39.001], [116.001, 39.001]], steps: [
  { start: 0, end: 1, road: '甲路' }, { start: 1, end: 2, road: '乙路' },
], breaks: [], distance: 198, labels: [] };
describe('navigation geometry', () => {
  it('reacquires a real position behind stale progress after signal recovery', () => {
    const result = matchPosition(route, [116, 39.0001], 180, true);
    expect(result.distance).toBeLessThan(.01);
    expect(result.progress).toBeCloseTo(11.1, 0);
  });
  it('matches real coordinates to traveled distance', () => {
    const match = matchPosition(route, [116, 39.0005]);
    expect(match.distance).toBeLessThan(.01);
    expect(match.progress).toBeCloseTo(55.6, 0);
  });
  it('keeps the current arm of a nearby loop using motion and route progress', () => {
    const xy = (x: number, y: number): [number,number] => [120+x/96300,30+y/111195];
    const loop: AppRoute = { ...route, path:[xy(0,0),xy(100,0),xy(100,20),xy(0,20)], breaks:[] };
    // This noisy fix is two metres closer to the return arm, 140 metres
    // farther along the route. The vehicle is still moving east on entry.
    const result=matchPosition(loop,xy(40,11),40,false,{heading:90,speed:10,accuracy:12});
    expect(result.index).toBe(0);
    expect(result.progress).toBeCloseTo(40,0);
    expect(result.distance).toBeCloseTo(11,0);
  });
  it('gives a right turn for north then east', () => {
    expect(instruction(route, 30).text).toBe('右转');
    expect(instruction(route, 30).road).toBe('乙路');
    expect(instruction(route, 150).text).toBe('到达目的地附近');
  });
  it('previews two consecutive actions with distance measured after the first turn', () => {
    const turns: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.001, 39.001], [116.001, 39.002]],
      steps: [{ start: 0, end: 1, road: '甲路', maneuver: 'right' },
        { start: 1, end: 2, road: '乙路', maneuver: 'left' },
        { start: 2, end: 3, road: '丙路' }] };
    const lengths = cumulative(turns), first = upcomingInstructions(turns, 30);
    expect(first[0]).toEqual(instruction(turns, 30));
    expect(first[1]).toMatchObject({ arrow: 'left', text: '左转', road: '丙路', key: 1 });
    expect(first[1].distance).toBeCloseTo(lengths[2] - lengths[1], 5);
    expect(upcomingInstructions(turns, 60)[1]).toEqual(first[1]);
    const advanced = upcomingInstructions(turns, lengths[1] + 10);
    expect(advanced[0]).toMatchObject({ arrow: 'left', key: 1 });
    expect(advanced[1]).toMatchObject({ arrow: 'destination' });
    expect(advanced[1].distance).toBeCloseTo(lengths[3] - lengths[2], 5);
    expect(upcomingInstructions(turns, lengths[2] + 10)).toHaveLength(1);
  });
  it('does not skip a closely spaced second action using the current-action arrival tolerance', () => {
    const short: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.00002, 39.001], [116.00002, 39.002]],
      steps: [{ start: 0, end: 1, road: '入口路', maneuver: 'right' },
        { start: 1, end: 2, road: '连接路', maneuver: 'bear-left' },
        { start: 2, end: 3, road: '出口路' }] };
    const actions = upcomingInstructions(short, 30);
    expect(actions[1]).toMatchObject({ arrow: 'bear-left', text: '靠左行驶', key: 1 });
    expect(actions[1].distance).toBeGreaterThan(0);
    expect(actions[1].distance).toBeLessThan(5);
  });
  it.each([
    ['left', '左转', 2], ['right', '右转', 3],
    ['sharp-left', '向左后方转弯', 6], ['sharp-right', '向右后方转弯', 7],
    ['uturn-left', '掉头', 8], ['uturn-right', '向右掉头', 19],
    ['straight', '继续直行', 9],
  ] as [NavigationManeuver, string, number][])('preserves explicit %s for the guide, original arrow and speech despite conflicting geometry', (maneuver, text, icon) => {
    const explicit: AppRoute = {...route, steps: [{...route.steps[0], maneuver}, route.steps[1]]};
    const turn = instruction(explicit, 30);
    expect(turn).toMatchObject({text, maneuver, arrow: maneuver});
    expect(navigationArrowAsset(turn.arrow)).toBe(`/amap/navigation-arrows/action-${icon}.webp`);
    expect(navigationVoicePhrase(turn, true)).toBe(`请${text}`);
  });
  it.each([
    [-170, 'uturn-left', 8], [170, 'uturn-right', 19],
    [-135, 'sharp-left', 6], [135, 'sharp-right', 7],
    [-90, 'left', 2], [90, 'right', 3], [0, 'straight', 9],
  ])('selects directional fallback arrows at %s degrees only without a route action', (angle, maneuver, icon) => {
    const radians = Number(angle) * Math.PI / 180;
    const bent: AppRoute = {...route, path: [route.path[0], route.path[1],
      [116 + Math.sin(radians) * .001 / Math.cos(39.001 * Math.PI / 180), 39.001 + Math.cos(radians) * .001]]};
    const turn = instruction(bent, 30);
    expect(turn.arrow).toBe(maneuver);
    expect(navigationArrowAsset(turn.arrow)).toBe(`/amap/navigation-arrows/action-${icon}.webp`);
  });
  it('keeps the destination arrow distinct from straight ahead', () => {
    const turn = instruction(route, 150);
    expect(turn).toMatchObject({text: '到达目的地附近', arrow: 'destination'});
    expect(navigationArrowAsset(turn.arrow)).toBe('/amap/navigation-arrows/action-15.webp');
  });
  it('uses the route maneuver for shallow forks instead of saying straight', () => {
    const fork: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.00005, 39.002]],
      steps: [{ start: 0, end: 1, road: '主路', maneuver: 'bear-right' }, { start: 1, end: 2, road: '右侧岔路' }] };
    expect(instruction(fork, 30)).toMatchObject({text: '靠右行驶', arrow: 'bear-right'});
    fork.steps[0].maneuver = 'bear-left';
    expect(instruction(fork, 30)).toMatchObject({text: '靠左行驶', arrow: 'bear-left'});
    fork.steps[0].maneuver = undefined;
    expect(instruction(fork, 30).text).toBe('继续直行');
  });
  it('distinguishes the three branches from a straight road', () => {
    const fork: AppRoute = { ...route, steps: [{ start: 0, end: 1, road: '主路', maneuver: 'fork-middle' },
      { start: 1, end: 2, road: '中间岔路' }] };
    expect(instruction(fork, 30)).toMatchObject({text: '走中间岔路', arrow: 'fork-middle'});
    fork.steps[0].maneuver = 'fork-left';
    expect(instruction(fork, 30)).toMatchObject({text: '走左侧岔路', arrow: 'fork-left'});
    fork.steps[0].maneuver = 'fork-right';
    expect(instruction(fork, 30)).toMatchObject({text: '走右侧岔路', arrow: 'fork-right'});
    const straight: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116, 39.002]] };
    expect(instruction(straight, 30).text).toBe('继续直行');
  });
  it('does not match or interpolate an omitted junction connector', () => {
    const disconnected: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.01, 39.001], [116.011, 39.001]], breaks: [2] };
    const lengths = cumulative(disconnected);
    expect(lengths[2]).toBe(lengths[1]);
    expect(matchPosition(disconnected, [116.005, 39.001]).distance).toBeGreaterThan(400);
    expect(pointAt(disconnected, lengths[1] + 1)[0]).toBeGreaterThanOrEqual(116.01);
  });
  it('announces the ring exit before entering and inside the ring despite a right-turn angle', () => {
    const ring: AppRoute = { ...route, path: [[116, 39], [116, 39.001], [116.001, 39.001], [116.001, 39.002]],
      steps: [{ start: 0, end: 1, road: '入口路', maneuver: 'roundabout-enter' },
        { start: 1, end: 2, road: '环岛', maneuver: 'roundabout-exit', roundaboutExit: 4 },
        { start: 2, end: 3, road: '出口路' }] };
    expect(instruction(ring, 30)).toMatchObject({ text: '进入环岛，从第4出口驶出', arrow: 'roundabout-enter', road: '环岛' });
    expect(instruction(ring, 120)).toMatchObject({ text: '从第4出口驶出环岛', arrow: 'roundabout-exit', road: '出口路' });
    expect(upcomingInstructions(ring, 30)[1]).toMatchObject({ text: '从第4出口驶出环岛', arrow: 'roundabout-exit', road: '出口路' });
    delete ring.steps[1].roundaboutExit;
    expect(instruction(ring, 30).text).toBe('进入环岛');
    expect(instruction(ring, 120).text).toBe('驶出环岛');
  });
  it('clamps replay at the destination', () => {
    expect(pointAt(route, 10000)).toEqual(route.path[2]);
  });
});
