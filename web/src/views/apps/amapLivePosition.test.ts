import { describe, expect, it } from 'vitest';
import { createLivePositionGate } from './amapLivePosition';
const fix = (timestamp: number) => ({ timestamp, latitude: 30.2, longitude: 120.2, accuracy: 1.3 });
describe('vehicle H5 position stream', () => {
  it('accepts continuing vehicle fixes including stationary positions', () => {
    const gate = createLivePositionGate();
    for (let i = 100000; i < 200000; i += 1000) expect(gate.accept(fix(i), i).accepted).toBe(true);
  });
  it('does not allow polling cache or out of order watch events to revive a lost fix', () => {
    const gate = createLivePositionGate(); gate.accept(fix(100000), 100000);
    expect(gate.accept(fix(100000), 110000).reason).toBe('duplicate');
    expect(gate.accept(fix(99000), 110000).accepted).toBe(false);
    expect(gate.accept(fix(100000), 120000).reason).toBe('invalid');
    expect(gate.accept(fix(121000), 121000)).toMatchObject({ accepted: true, recovered: true });
  });
  it('rejects invalid precision and future timestamps', () => {
    const gate = createLivePositionGate();
    expect(gate.accept({ ...fix(100000), accuracy: NaN }, 100000).accepted).toBe(false);
    expect(gate.accept(fix(110000), 100000).accepted).toBe(false);
  });
});
