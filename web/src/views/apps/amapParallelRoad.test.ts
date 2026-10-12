import { describe, expect, it } from 'vitest';
import { directRoadSwitchTargets, findParallelRoute, parallelRoadProperty } from './amapParallelRoad';
import type { AppRoute } from './amapNavigation';

const origin: [number, number] = [120, 30];
function route(id: number, road: string, offset = 0): AppRoute {
  return { id, path: [[120 + offset, 30], [120 + offset, 30.01]],
    steps: [{ start: 0, end: 1, road }], breaks: [], distance: 1110, labels: [] };
}

describe('manual parallel road correction', () => {
  it.each([[1, 'main'], [3, 'main'], [6, 'main'], [8, 'main'], [5, 'side'], [7, 'side']] as const)(
    'uses APK native property %s for %s classification', (property, kind) => {
      expect(parallelRoadProperty(property)).toBe(kind);
    });
  it('does not classify unverified road properties', () => {
    for (const property of [undefined, -1, 0, 2, 4, 15, 18, 100]) expect(parallelRoadProperty(property)).toBeUndefined();
  });
  it('switches same-name links by native property and exact uint64 ID', () => {
    const main = { ...route(0, 'XX路'), roadLinks: [{ start: 0, end: 1, road: 'XX路', id: '9007199254740992', roadProperty: 1 }] };
    const side = { ...route(1, 'XX路'), roadLinks: [{ start: 0, end: 1, road: 'XX路', id: '9007199254740993', roadProperty: 7 }] };
    expect(findParallelRoute([main, side], main, origin, 'side')).toBe(1);
    expect(findParallelRoute([main, side], side, origin, 'main')).toBe(0);
    const duplicate = { ...side, roadLinks: [{ ...side.roadLinks[0], id: main.roadLinks[0].id }] };
    expect(findParallelRoute([main, duplicate], main, origin, 'side')).toBe(-1);
  });
  it('accepts a classified unnamed link and prioritizes native property over a conflicting name', () => {
    const main = { ...route(0, '道路'), roadLinks: [{ start: 0, end: 1, road: '', id: '1', roadProperty: 1 }] };
    const side = { ...route(1, '主路'), roadLinks: [{ start: 0, end: 1, road: '主路', id: '2', roadProperty: 7 }] };
    expect(findParallelRoute([main, side], main, origin, 'side')).toBe(1);
    expect(findParallelRoute([main, side], side, origin, 'main')).toBe(0);
  });
  it('uses the outgoing native link within a step and does not inherit a tunnel name into an unnamed link', () => {
    const layered = { ...route(0, 'XX路'), path: [[120, 30], [120, 30.005], [120, 30.01]] as [number, number][],
      steps: [{ start: 0, end: 2, road: 'XX路' }], roadLinks: [
        { start: 0, end: 1, road: 'XX路', id: '1' }, { start: 1, end: 2, road: 'XX隧道', id: '2' }] };
    const surface = { ...route(1, 'XX路'), roadLinks: [{ start: 0, end: 1, road: 'XX路', id: '3' }] };
    expect(findParallelRoute([layered, surface], layered, [120, 30.005], 'ground')).toBe(1);
    layered.roadLinks[1].road = '';
    expect(findParallelRoute([layered, surface], layered, [120, 30.007], 'ground')).toBe(-1);
  });
  it('chooses an explicitly labelled side road near the vehicle', () => {
    const main = route(0, '主路'), side = route(1, 'XX路辅路', .00015);
    expect(findParallelRoute([main, side], main, origin, 'side')).toBe(1);
  });
  it('can return from a side road to an unlabelled main road', () => {
    const main = route(0, 'XX路'), side = route(1, 'XX路辅路', .00015);
    expect(findParallelRoute([main, side], side, origin, 'main')).toBe(0);
  });
  it('distinguishes stacked elevated and ground routes by road name', () => {
    const elevated = route(0, 'XX高架'), ground = route(1, 'XX路地面道路');
    expect(findParallelRoute([elevated, ground], elevated, origin, 'ground')).toBe(1);
    expect(findParallelRoute([elevated, ground], ground, origin, 'elevated')).toBe(0);
  });
  it('switches coincident unnamed surface, tunnel, bridge and elevated links by APK link type', () => {
    const nativeRoute = (id: number, linkType: number): AppRoute => ({ ...route(id, '道路'),
      roadLinks: [{ start: 0, end: 1, road: '', id: String(id + 1), linkType }] });
    const ground = nativeRoute(0, 0), tunnel = nativeRoute(1, 2);
    for (const raisedType of [3, 4]) {
      const raised = nativeRoute(2, raisedType);
      expect(findParallelRoute([raised, ground, tunnel], raised, origin, 'ground')).toBe(1);
      expect(findParallelRoute([ground, tunnel, raised], ground, origin, 'elevated')).toBe(2);
      expect(findParallelRoute([raised, ground, tunnel], raised, origin, 'tunnel')).toBe(2);
    }
    expect(findParallelRoute([ground, tunnel], ground, origin, 'tunnel')).toBe(1);
    expect(findParallelRoute([ground, tunnel], tunnel, origin, 'ground')).toBe(0);
    const duplicate = { ...ground, roadLinks: [{ ...ground.roadLinks![0], id: tunnel.roadLinks![0].id }] };
    expect(findParallelRoute([duplicate], tunnel, origin, 'ground')).toBe(-1);
  });
  it('prioritizes the native layer type and rejects ferries or unknown types as surface alternatives', () => {
    const tunnel = { ...route(0, '同名路'), roadLinks: [{ start: 0, end: 1, road: '同名路', id: '1', linkType: 2 }] };
    const surface = { ...route(1, '名称含隧道'), roadLinks: [{ start: 0, end: 1, road: '名称含隧道', id: '2', linkType: 0 }] };
    expect(findParallelRoute([tunnel, surface], tunnel, origin, 'ground')).toBe(1);
    for (const linkType of [-1, 1, 5, 100]) {
      const unknown = { ...surface, roadLinks: [{ ...surface.roadLinks[0], road: '地面路', linkType }] };
      expect(findParallelRoute([unknown], tunnel, origin, 'ground')).toBe(-1);
    }
    surface.roadLinks[0].linkType = 2;
    expect(findParallelRoute([surface], tunnel, origin, 'ground')).toBe(-1);
  });
  it('does not pretend an unlabelled or distant road is a known alternative', () => {
    const current = route(0, 'XX路'), unknown = route(1, 'YY路', .00015);
    expect(findParallelRoute([current, unknown], current, origin, 'side')).toBe(-1);
    expect(findParallelRoute([current, route(2, 'XX路辅路', .002)], current, origin, 'side')).toBe(-1);
  });
  it('rejects a nearby opposite-direction carriageway', () => {
    const current = route(0, '主路');
    const reverse = route(1, 'XX路辅路', .0001);
    reverse.path.reverse();
    expect(findParallelRoute([current, reverse], current, origin, 'side')).toBe(-1);
  });
  it('switches between named surface and tunnel routes with identical map coordinates', () => {
    const ground = route(0, '环城路地面道路'), tunnel = route(1, '环城隧道');
    expect(findParallelRoute([ground, tunnel], ground, origin, 'tunnel')).toBe(1);
    expect(findParallelRoute([ground, tunnel], tunnel, origin, 'ground')).toBe(0);
  });
  it('can return from a tunnel to a named ordinary surface road', () => {
    const tunnel = route(0, '环城隧道'), surface = route(1, '环城路');
    const elevated = route(2, '环城高架'), otherTunnel = route(3, '城东隧道');
    expect(findParallelRoute([tunnel, elevated, otherTunnel, surface], tunnel, origin, 'ground')).toBe(3);
    expect(findParallelRoute([tunnel, route(4, '道路'), route(5, '')], tunnel, origin, 'ground')).toBe(-1);
  });
  it.each(['城西地道', '城西地下道路', '城西下穿通道'])('recognizes %s as an underground alternative', name => {
    const ground = route(0, '城西路'), underground = route(1, name);
    expect(findParallelRoute([ground, underground], ground, origin, 'tunnel')).toBe(1);
    expect(findParallelRoute([ground, underground], underground, origin, 'ground')).toBe(0);
  });
  it('does not select an elevated road, surface road, distant tunnel or reverse tunnel as a tunnel', () => {
    const ground = route(0, 'XX路'), reverse = route(3, 'XX隧道', .0001);
    reverse.path.reverse();
    expect(findParallelRoute([ground, route(1, 'XX高架'), route(2, 'YY路'), reverse, route(4, 'YY隧道', .002)],
      ground, origin, 'tunnel')).toBe(-1);
  });
  it('uses the outgoing road at a shared step endpoint', () => {
    const tunnel = { ...route(0, '道路'), path: [[120, 30], [120, 30.005], [120, 30.01]] as [number, number][],
      steps: [{ start: 0, end: 1, road: 'XX路地面道路' }, { start: 1, end: 2, road: 'XX隧道' }] };
    const surface = route(1, 'XX路');
    expect(findParallelRoute([tunnel, surface], tunnel, [120, 30.005], 'ground')).toBe(1);
  });
});

describe('direct road-switch targets', () => {
  const native = (id: number, roadProperty?: number, linkType?: number): AppRoute => ({ ...route(id, '同名路'),
    roadLinks: [{ start: 0, end: 1, road: '同名路', id: String(id + 1), roadProperty, linkType }] });

  it('inverts the native main/side target independently of the bridge target', () => {
    const main = native(0, 1, 3), side = native(1, 7, 2);
    expect(directRoadSwitchTargets(main, origin, [main])).toEqual(['side', 'ground']);
    expect(directRoadSwitchTargets(side, origin, [side])).toEqual(['main', 'ground']);
  });

  it('uses confirmed ground alternatives when present and offers explicit layer requests otherwise', () => {
    const ground = native(0, undefined, 0), tunnel = native(1, undefined, 2), bridge = native(2, undefined, 4);
    expect(directRoadSwitchTargets(ground, origin, [ground, tunnel])).toEqual(['tunnel']);
    expect(directRoadSwitchTargets(ground, origin, [ground, bridge])).toEqual(['elevated']);
    expect(directRoadSwitchTargets(ground, origin, [ground])).toEqual(['elevated', 'tunnel']);
  });

  it('does not invent a target when the current road has no classified axes or confirmed candidates', () => {
    const unknown = route(0, '道路');
    expect(directRoadSwitchTargets(unknown, origin, [unknown, route(1, '另一条路')])).toEqual([]);
    const ferry = native(0, undefined, 1);
    expect(directRoadSwitchTargets(ferry, origin, [ferry])).toEqual([]);
    const side = native(1, 7);
    expect(directRoadSwitchTargets(unknown, origin, [unknown, side])).toEqual(['side']);
  });

  it('does not offer an unconfirmed candidate for an unknown axis', () => {
    const unknown = native(0), duplicate = native(0, undefined, 2);
    const reverse = native(1, 7), distant = native(2, undefined, 4);
    reverse.path.reverse();
    distant.path = [[120.002, 30], [120.002, 30.01]];
    expect(directRoadSwitchTargets(unknown, origin, [duplicate, reverse, distant])).toEqual([]);
  });

  it('changes the target as the car enters the outgoing link instead of retaining the old road state', () => {
    const layered: AppRoute = { ...route(0, '道路'), path: [[120, 30], [120, 30.005], [120, 30.01]],
      steps: [{ start: 0, end: 2, road: '同名路' }], roadLinks: [
        { start: 0, end: 1, road: '同名路', id: '1', roadProperty: 1, linkType: 0 },
        { start: 1, end: 2, road: '同名路', id: '2', roadProperty: 7, linkType: 2 }] };
    expect(directRoadSwitchTargets(layered, origin, [layered])).toEqual(['side', 'elevated', 'tunnel']);
    expect(directRoadSwitchTargets(layered, [120, 30.005], [layered])).toEqual(['main', 'ground']);
    expect(directRoadSwitchTargets(layered, [NaN, 30], [layered])).toEqual([]);
  });
});
