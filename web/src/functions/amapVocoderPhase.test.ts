import { describe, expect, it } from 'vitest';
import { amapVocoderPhase } from './amapVocoderPhase';

describe('AMap vocoder phase', () => {
  it('integrates F0 and samples phase at frame boundaries', () => {
    const result = amapVocoderPhase(new Float32Array(480).fill(200));
    expect(result.phaseSamples[0]).toBeCloseTo(200.001 / 24000, 6);
    expect(result.phaseFrames[0]).toBeCloseTo(result.phaseSamples[0] * 2 * Math.PI, 6);
    expect(result.phaseFrames[1]).toBeCloseTo(result.phaseSamples[240] * 2 * Math.PI, 6);
    expect(result.phaseSamples[240]).toBeGreaterThanOrEqual(-0.5);
    expect(result.phaseSamples[240]).toBeLessThan(0.5);
  });
});
