import { amapIstft, amapStft } from './amapIstft';

const sampleRate = 24000;
const fftLength = 1200;
const hopLength = 240;
const bins = fftLength / 2 + 1;
const window = Float32Array.from({ length: fftLength }, (_, i) =>
  0.5 - 0.5 * Math.cos(2 * Math.PI * i / fftLength));

export type AmapVocoderControls = {
  hMag: Float32Array;
  hPhase: Float32Array;
  nMag: Float32Array;
  nPhase: Float32Array;
  phaseSamples: Float32Array;
  f0Samples: Float32Array;
};

function whiteNoise(length: number): Float32Array {
  const result = new Float32Array(length);
  for (let i = 0; i < length; i += 2) {
    const first = Math.max(Number.MIN_VALUE, Math.random());
    const angle = 2 * Math.PI * Math.random();
    const radius = Math.sqrt(-2 * Math.log(first));
    result[i] = radius * Math.cos(angle);
    if (i + 1 < length) result[i + 1] = radius * Math.sin(angle);
  }
  return result;
}

/** Rebuilds PCM from AMap's DDSPGAN V2 controls without calling the APK library. */
export function amapVocoderDsp(
  controls: AmapVocoderControls,
  referenceNoiseSpectrum?: Float32Array,
): Float32Array {
  const { hMag, hPhase, nMag, nPhase, phaseSamples, f0Samples } = controls;
  const frames = hMag.length / bins;
  if (!Number.isInteger(frames) || frames < 1 ||
    hPhase.length !== hMag.length || nMag.length !== hMag.length || nPhase.length !== hMag.length ||
    phaseSamples.length !== frames * hopLength || f0Samples.length !== phaseSamples.length)
    throw new Error('高德声码器张量形状不匹配');

  const excitation = new Float32Array(phaseSamples.length);
  for (let i = 0; i < excitation.length; i++) {
    const cycle = Math.fround(phaseSamples[i] * sampleRate / (f0Samples[i] + 0.001));
    const angle = cycle * Math.PI;
    excitation[i] = cycle === 0 ? 1 : Math.sin(angle) / angle;
  }
  const excitationSpectrum = amapStft(excitation, window, fftLength, hopLength);
  const noiseSpectrum = referenceNoiseSpectrum ||
    amapStft(whiteNoise(phaseSamples.length), window, fftLength, hopLength);
  const spectraLength = (frames + 1) * bins * 2;
  if (excitationSpectrum.length !== spectraLength || noiseSpectrum.length !== spectraLength)
    throw new Error('高德声码器激励频谱长度不匹配');
  const combined = new Float32Array(spectraLength);
  for (let frame = 0; frame <= frames; frame++) {
    const modelFrame = Math.min(frame, frames - 1);
    for (let bin = 0; bin < bins; bin++) {
      const modelIndex = modelFrame * bins + bin;
      const index = (frame * bins + bin) * 2;
      const harmonicMagnitude = Math.exp(hMag[modelIndex]);
      const harmonicAngle = Math.fround(hPhase[modelIndex] * Math.PI);
      const harmonicRe = harmonicMagnitude * Math.cos(harmonicAngle);
      const harmonicIm = harmonicMagnitude * Math.sin(harmonicAngle);
      const noiseMagnitude = Math.exp(nMag[modelIndex]) / 128;
      const noiseAngle = Math.fround(nPhase[modelIndex] * Math.PI);
      const noiseRe = noiseMagnitude * Math.cos(noiseAngle);
      const noiseIm = noiseMagnitude * Math.sin(noiseAngle);
      const excitationRe = excitationSpectrum[index], excitationIm = excitationSpectrum[index + 1];
      const sourceRe = noiseSpectrum[index], sourceIm = noiseSpectrum[index + 1];
      combined[index] = harmonicRe * excitationRe - harmonicIm * excitationIm +
        noiseRe * sourceRe - noiseIm * sourceIm;
      combined[index + 1] = harmonicRe * excitationIm + harmonicIm * excitationRe +
        noiseRe * sourceIm + noiseIm * sourceRe;
    }
  }
  const samples = amapIstft(combined, window, fftLength, hopLength);
  let peak = 0;
  for (const sample of samples) peak = Math.max(peak, Math.abs(sample));
  if (peak > 1) {
    const scale = 0.99 / peak;
    for (let i = 0; i < samples.length; i++) samples[i] *= scale;
  }
  return samples;
}
