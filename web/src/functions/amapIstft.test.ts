import { describe, expect, it } from 'vitest';
import { amapIstft, amapStft } from './amapIstft';

describe('AMap inverse STFT', () => {
  it('reconstructs a 24 kHz signal with the native 1200/240 Hann settings', () => {
    const signal = Float32Array.from({ length: 2400 }, (_, i) =>
      0.2 * Math.sin(2 * Math.PI * 217 * i / 24000) +
      0.1 * Math.cos(2 * Math.PI * 1831 * i / 24000));
    const window = Float32Array.from({ length: 1200 }, (_, i) =>
      0.5 - 0.5 * Math.cos(2 * Math.PI * i / 1200));
    const reconstructed = amapIstft(amapStft(signal, window), window);
    expect(reconstructed.length).toBe(signal.length);
    let maxError = 0;
    for (let i = 0; i < signal.length; i++)
      maxError = Math.max(maxError, Math.abs(reconstructed[i] - signal[i]));
    expect(maxError).toBeLessThan(1e-6);
  });
});
