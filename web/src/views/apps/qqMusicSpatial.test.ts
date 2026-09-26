// @vitest-environment node
import { expect, it } from 'vitest';
import { roomImpulse, outputCandidates, routeSpatialOutput } from './qqMusicSpatial';
it('builds finite decorrelated stereo tails with delayed onset and decay', () => {
  for (const mode of ['room', 'hall'] as const) {
    const [left, right] = roomImpulse(48000, mode);
    expect(left.length).toBe(Math.ceil(48000 * (mode === 'hall' ? 1.6 : .55)));
    expect(right.length).toBe(left.length);
    expect(left.every(Number.isFinite)).toBe(true);
    expect(left.slice(0, 400).every(x => x === 0)).toBe(true);
    expect(left).not.toEqual(right);
    const energy = (values: Float32Array) => values.reduce((sum, x) => sum + x * x, 0);
    expect(energy(left.slice(-4000))).toBeLessThan(energy(left.slice(1000, 5000)) * .01);
  }
});
it('rejects unsupported sample rates', () => {
  expect(() => roomImpulse(NaN, 'room')).toThrow();
  expect(() => roomImpulse(0, 'hall')).toThrow();
});

function mockAudio(accepted: number[], failEight = false) {
 const attempts: number[] = [];
 const node = () => ({ connect: () => {}, disconnect: () => {}, gain: { value: 0 }, frequency: { value: 0 }, Q: { value: 0 }, delayTime: { value: 0 } });
 let count = 2;
 const destination = { maxChannelCount: 8, channelInterpretation: 'speakers', get channelCount() { return count; }, set channelCount(value: number) { attempts.push(value); if (!accepted.includes(value)) throw new Error('Unsupported'); count = value; } };
 const ctx = { destination, createChannelSplitter: node, createChannelMerger: (size: number) => { if (size === 8 && failEight) throw new Error('Failed graph'); return node(); }, createGain: node, createDelay: node, createBiquadFilter: node };
 return { ctx: ctx as unknown as AudioContext, dry: node() as unknown as AudioNode, wet: node() as unknown as AudioNode, attempts };
}
it('falls back from rejected 7.1 to 5.1 and stereo', () => {
 for (const [accepted, expected] of [[[6,2],6], [[2],2], [[8,6,2],8]] as [number[], number][]) {
  const test = mockAudio(accepted);
  const result = routeSpatialOutput(test.ctx, test.dry, test.wet, true);
  expect(result.channels).toBe(expected); result.dispose();
 }
 const test = mockAudio([8,6,2], true);
 expect(routeSpatialOutput(test.ctx, test.dry, test.wet, true).channels).toBe(6);
});
it('uses stereo for compatibility mode and surfaces total failure', () => {
 expect(outputCandidates(2,true)).toEqual([2]);
 expect(outputCandidates(6,true)).toEqual([6,2]);
 const stereo = mockAudio([8,6,2]);
 expect(routeSpatialOutput(stereo.ctx, stereo.dry, stereo.wet, false).channels).toBe(2);
 expect(stereo.attempts).toEqual([2]);
 const fail = mockAudio([]);
 expect(() => routeSpatialOutput(fail.ctx, fail.dry, fail.wet, true)).toThrow('Audio output unavailable');
});
