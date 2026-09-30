const sampleRate = 24000;
const hopLength = 240;

export type AmapVocoderPhase = {
  phaseSamples: Float32Array;
  phaseFrames: Float32Array;
};

/** Integrates the F0 model's sample-rate output into the ctrl model's phase input. */
export function amapVocoderPhase(f0Samples: Float32Array): AmapVocoderPhase {
  if (f0Samples.length < hopLength || f0Samples.length % hopLength !== 0)
    throw new Error('高德基频张量形状不匹配');
  const phaseSamples = new Float32Array(f0Samples.length);
  const phaseFrames = new Float32Array(f0Samples.length / hopLength);
  let cycles = 0;
  for (let i = 0; i < f0Samples.length; i++) {
    const f0 = f0Samples[i];
    if (!Number.isFinite(f0) || f0 < 0) throw new Error('高德基频张量无效');
    cycles += (f0 + 0.001) / sampleRate;
    const wrapped = cycles - Math.floor(cycles + 0.5);
    phaseSamples[i] = wrapped;
    if (i % hopLength === 0) phaseFrames[i / hopLength] = wrapped * (2 * Math.PI);
  }
  return { phaseSamples, phaseFrames };
}
