import { describe, expect, it } from 'vitest';
import { cameraEventAhead, createSpeedLimitSectionEvents, createSpeedReminder, isOverSpeed, speedWarningLevel, speedLimitAt, upcomingSpeedCamera, upcomingSpeedLimit, upcomingSpeedSign } from './amapSpeedLimit';

describe('navigation road speed limit', () => {
  it('never treats an absent or invalid limit as a real speed sign', () => {
    expect(speedLimitAt(undefined, 100)).toBeUndefined();
    expect(speedLimitAt([{ start: 0, end: 200, limit: 0 }], 100)).toBeUndefined();
    expect(isOverSpeed(111, undefined)).toBe(false);
  });
  it('matches a bounded route section and uses the App 1.1 default', () => {
    const section = { start: 100, end: 250, limit: 80 };
    expect(speedLimitAt([section], 99)).toBeUndefined();
    expect(speedLimitAt([section], 100)).toEqual(section);
    expect(speedLimitAt([section], 250)).toBeUndefined();
    expect(upcomingSpeedLimit([section], 0)).toEqual({ section, distance: 100 });
    expect(upcomingSpeedLimit([section], 100)).toBeUndefined();
    expect(isOverSpeed(87, 80)).toBe(false);
    expect(isOverSpeed(89, 80)).toBe(true);
  });
  it('reserves the edge warning for serious excess over a known road limit',()=>{
    expect(speedWarningLevel(0,80)).toBe(0);
    expect(speedWarningLevel(87,80)).toBe(0);
    expect(speedWarningLevel(89,80)).toBe(1);
    expect(speedWarningLevel(103,80)).toBe(1);
    expect(speedWarningLevel(104,80)).toBe(2);
    expect(speedWarningLevel(49,30)).toBe(1);
    expect(speedWarningLevel(50,30)).toBe(2);
    expect(speedWarningLevel(150,undefined)).toBe(0);
    expect(speedWarningLevel(NaN,80)).toBe(0);
  });
  it('requires sustained overspeed and does not repeat on each GPS fix', () => {
    const section = { start: 100, end: 250, limit: 80 };
    const reminder = createSpeedReminder();
    expect(reminder.update(section, 111, 1000)).toBe(false);
    expect(reminder.update(section, 111, 4000)).toBe(true);
    expect(reminder.update(section, 111, 5000)).toBe(false);
    expect(reminder.update(undefined, 111, 6000)).toBe(false);
    expect(reminder.update(section, 111, 7000)).toBe(false);
    expect(reminder.update(section, 111, 10000)).toBe(true);
  });
  it('emits the APK section event only at verified road-section boundaries', () => {
    const a = { start: 100, end: 200, limit: 80 };
    const b = { start: 200, end: 300, limit: 60 };
    const events = createSpeedLimitSectionEvents();
    expect(events.update([a, b], 99)).toBeUndefined();
    expect(events.update([a, b], 100)).toEqual({ type: 452, speed: 80, section: a });
    expect(events.update([a, b], 199)).toBeUndefined();
    expect(events.update([a, b], 200)).toEqual({ type: 452, speed: 60, section: b });
    expect(events.update([a, b], 300)).toEqual({ type: 452, speed: 0, section: undefined });
    expect(events.update([a, b], 301)).toBeUndefined();
    events.reset();
    expect(events.update([a, b], 100)).toEqual({ type: 452, speed: 80, section: a });
    expect(events.update(undefined, 120)).toEqual({ type: 452, speed: 0, section: undefined });
  });
  it('keeps the APK camera event separate from the road-section event', () => {
    const camera = { at: 1000, type: 7 as const, speed: [60, 80, 255] };
    expect(upcomingSpeedCamera([camera], 0)).toEqual({ camera, distance: 1000, limit: 80 });
    expect(cameraEventAhead([camera], 800)).toEqual({ type: 95, naviCamera: [{ type: 7, speed: [60, 80, 255], distance: 200 }] });
    expect(cameraEventAhead([camera], 1001)).toEqual({ type: 95, naviCamera: [] });
    expect(upcomingSpeedCamera([{ at: 1000, type: 7, speed: [255] }], 800)).toBeUndefined();
    expect(upcomingSpeedCamera([{ at: 1000, type: 7, speed: [120] }], -1500)).toBeUndefined();
    expect(upcomingSpeedCamera([camera, { at: 900, type: 25, speed: [60] }], 800)?.limit).toBe(60);
  });
  it('uses routeguide point signs only as upcoming alerts', () => {
    const signs = [{ at: 400, limit: 80 }, { at: 900, limit: 60 }];
    expect(upcomingSpeedSign(signs, 300)).toEqual({ sign: signs[0], distance: 100 });
    expect(upcomingSpeedSign(signs, 401)).toEqual({ sign: signs[1], distance: 499 });
    expect(upcomingSpeedSign(signs, 901)).toBeUndefined();
    expect(upcomingSpeedSign([{ at: 500, limit: 255 }], 400)).toBeUndefined();
  });
});
