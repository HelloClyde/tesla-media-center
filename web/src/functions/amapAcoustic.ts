const channels = 96;

export type AmapEncoderOutput = {
  roundedDurations: Int32Array;
  latent: Float32Array;
  linguistic: Float32Array;
};

export type AmapDecoderInput = {
  linguistic: Float32Array;
  durationEmbedding: Float32Array;
  speaker: Float32Array;
  environment: Float32Array;
  latent: Float32Array;
  frames: number;
};

/** Reproduces the APK's duration expansion and intra-phoneme positional encoding. */
export function amapExpandAcoustic(
  encoder: AmapEncoderOutput,
  speakerEmbedding: Float32Array,
  speedScale: number,
): AmapDecoderInput {
  const tokens = encoder.roundedDurations.length;
  if (tokens < 1 || encoder.latent.length !== tokens * channels ||
    encoder.linguistic.length !== tokens * channels || speakerEmbedding.length !== channels ||
    !Number.isFinite(speedScale) || speedScale <= 0)
    throw new Error('高德声学模型张量形状不匹配');

  const durations = Int32Array.from(encoder.roundedDurations,
    duration => Math.max(0, Math.ceil(duration * speedScale)));
  const frames = durations.reduce((sum, duration) => sum + duration, 0);
  if (frames < 1 || frames > 10000) throw new Error('高德声学模型时长无效');
  const linguistic = new Float32Array(frames * channels);
  const latent = new Float32Array(frames * channels);
  const speaker = new Float32Array(frames * channels);
  const environment = new Float32Array(frames * channels);
  const durationEmbedding = new Float32Array(frames * channels);
  let frame = 0;
  for (let token = 0; token < tokens; token++) {
    const duration = durations[token];
    for (let offset = 0; offset < duration; offset++, frame++) {
      const base = frame * channels;
      linguistic.set(encoder.linguistic.subarray(token * channels, (token + 1) * channels), base);
      latent.set(encoder.latent.subarray(token * channels, (token + 1) * channels), base);
      speaker.set(speakerEmbedding, base);
      const position = (offset + 1) / duration;
      for (let frequency = 0; frequency < channels / 2; frequency++) {
        const angle = position / Math.pow(10000, frequency / (channels / 2 - 1));
        durationEmbedding[base + frequency] = Math.sin(angle);
        durationEmbedding[base + frequency + channels / 2] = Math.cos(angle);
      }
    }
  }
  return { linguistic, durationEmbedding, speaker, environment, latent, frames };
}
