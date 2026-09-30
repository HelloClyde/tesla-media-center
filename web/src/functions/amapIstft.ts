/** The 1200-point, 240-hop inverse STFT used by AMap's default offline voice. */
type Complex = { re: Float64Array; im: Float64Array };
type Plan = { length: number; radix: number; child?: Plan; cos?: Float64Array; sin?: Float64Array };
const plans = new Map<number, Plan>();

function plan(length: number): Plan {
  let radix = 0;
  for (let divisor = 2; divisor * divisor <= length; divisor++) {
    if (length % divisor === 0) { radix = divisor; break; }
  }
  if (!radix) radix = length;
  if (length === 1) return { length, radix: 1 };
  const cos = new Float64Array(length * radix);
  const sin = new Float64Array(length * radix);
  for (let k = 0; k < length; k++) {
    for (let r = 0; r < radix; r++) {
      const angle = 2 * Math.PI * r * k / length;
      cos[k * radix + r] = Math.cos(angle);
      sin[k * radix + r] = Math.sin(angle);
    }
  }
  return { length, radix, child: radix === length ? undefined : plan(length / radix), cos, sin };
}

function inverseFft(input: Complex, fftPlan: Plan): Complex {
  const { length, radix, child, cos, sin } = fftPlan;
  if (length === 1) return input;
  const width = length / radix;
  const parts: Complex[] = [];
  for (let r = 0; r < radix; r++) {
    const re = new Float64Array(width), im = new Float64Array(width);
    for (let i = 0; i < width; i++) {
      re[i] = input.re[i * radix + r];
      im[i] = input.im[i * radix + r];
    }
    parts.push(child ? inverseFft({ re, im }, child) : { re, im });
  }
  const re = new Float64Array(length), im = new Float64Array(length);
  for (let k = 0; k < length; k++) {
    const q = k % width;
    let real = 0, imaginary = 0;
    for (let r = 0; r < radix; r++) {
      const index = k * radix + r;
      real += parts[r].re[q] * cos![index] - parts[r].im[q] * sin![index];
      imaginary += parts[r].re[q] * sin![index] + parts[r].im[q] * cos![index];
    }
    re[k] = real;
    im[k] = imaginary;
  }
  return { re, im };
}

function fftPlan(length: number): Plan {
  let cached = plans.get(length);
  if (!cached) { cached = plan(length); plans.set(length, cached); }
  return cached;
}

/** Centered real STFT with the symmetric edge padding used by the native vocoder. */
export function amapStft(
  signal: Float32Array,
  window: Float32Array,
  fftLength = 1200,
  hopLength = 240,
): Float32Array {
  if (fftLength < 2 || fftLength % 2 || hopLength < 1 || window.length !== fftLength || signal.length < fftLength / 2)
    throw new Error('无效的高德声码器频谱输入');
  const half = fftLength / 2;
  const frames = Math.floor(signal.length / hopLength) + 1;
  const bins = half + 1;
  const spectrum = new Float32Array(frames * bins * 2);
  const transform = fftPlan(fftLength);
  for (let frame = 0; frame < frames; frame++) {
    const re = new Float64Array(fftLength), im = new Float64Array(fftLength);
    for (let i = 0; i < fftLength; i++) {
      const position = frame * hopLength + i - half;
      const reflected = position < 0 ? -position - 1 :
        position >= signal.length ? signal.length * 2 - position - 1 : position;
      re[i] = signal[reflected] * window[i];
    }
    const result = inverseFft({ re, im }, transform);
    const offset = frame * bins * 2;
    for (let bin = 0; bin < bins; bin++) {
      spectrum[offset + bin * 2] = result.re[bin];
      spectrum[offset + bin * 2 + 1] = -result.im[bin];
    }
  }
  return spectrum;
}

/** Interleaved complex spectra: frame, bin, real/imaginary. Output is mono 24 kHz PCM float. */
export function amapIstft(
  spectra: Float32Array,
  window: Float32Array,
  fftLength = 1200,
  hopLength = 240,
): Float32Array {
  if (fftLength < 2 || fftLength % 2 || hopLength < 1 || window.length !== fftLength)
    throw new Error('无效的高德声码器窗参数');
  const bins = fftLength / 2 + 1;
  const floatsPerFrame = bins * 2;
  if (!spectra.length || spectra.length % floatsPerFrame)
    throw new Error('无效的高德声码器频谱');
  const frames = spectra.length / floatsPerFrame;
  const fullLength = (frames - 1) * hopLength + fftLength;
  const output = new Float64Array(fullLength);
  const denominator = new Float64Array(fullLength);
  const transform = fftPlan(fftLength);
  for (let frame = 0; frame < frames; frame++) {
    const re = new Float64Array(fftLength), im = new Float64Array(fftLength);
    const offset = frame * floatsPerFrame;
    for (let bin = 0; bin < bins; bin++) {
      re[bin] = spectra[offset + bin * 2];
      im[bin] = spectra[offset + bin * 2 + 1];
    }
    for (let bin = bins; bin < fftLength; bin++) {
      re[bin] = re[fftLength - bin];
      im[bin] = -im[fftLength - bin];
    }
    const samples = inverseFft({ re, im }, transform).re;
    for (let i = 0; i < fftLength; i++) {
      const at = frame * hopLength + i;
      output[at] += samples[i] * window[i] / fftLength;
      denominator[at] += window[i] * window[i];
    }
  }
  const trim = fftLength / 2;
  const length = fullLength - trim * 2;
  const pcm = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const at = i + trim;
    pcm[i] = denominator[at] > 1e-10 ? output[at] / denominator[at] : 0;
  }
  return pcm;
}
