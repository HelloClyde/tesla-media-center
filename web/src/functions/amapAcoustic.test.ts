import { describe, expect, it } from 'vitest';
import { amapExpandAcoustic } from './amapAcoustic';

describe('AMap acoustic expansion', () => {
  it('scales durations and builds per-phoneme sinusoidal positions', () => {
    const output = amapExpandAcoustic({
      roundedDurations: new Int32Array([11, 14]),
      latent: Float32Array.from({ length: 192 }, (_, i) => i < 96 ? 1 : 2),
      linguistic: Float32Array.from({ length: 192 }, (_, i) => i < 96 ? 3 : 4),
    }, new Float32Array(96).fill(0.5), 1.18);
    expect(output.frames).toBe(30);
    expect(output.latent[12 * 96]).toBe(1);
    expect(output.latent[13 * 96]).toBe(2);
    expect(output.linguistic[13 * 96]).toBe(4);
    expect(output.durationEmbedding[0]).toBeCloseTo(Math.sin(1 / 13), 6);
    expect(output.durationEmbedding[12 * 96]).toBeCloseTo(Math.sin(1), 6);
    expect(output.durationEmbedding[13 * 96]).toBeCloseTo(Math.sin(1 / 17), 6);
    expect(output.durationEmbedding[48]).toBeCloseTo(Math.cos(1 / 13), 6);
    expect(output.speaker[29 * 96]).toBe(0.5);
    expect(output.environment.some(value => value !== 0)).toBe(false);
  });
});
