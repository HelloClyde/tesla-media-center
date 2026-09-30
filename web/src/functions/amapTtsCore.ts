import { amapExpandAcoustic } from './amapAcoustic';
import { amapVocoderDsp } from './amapVocoderDsp';
import { amapVocoderPhase } from './amapVocoderPhase';

type Tensor = Int32Array | Float32Array;
type ModelKind = 0 | 1 | 2 | 3;

export type AmapMnnModule = {
  HEAPU8: Uint8Array;
  HEAPF32: Float32Array;
  HEAP32: Int32Array;
  _malloc(bytes: number): number;
  _free(address: number): void;
  _amap_mnn_load(kind: number, address: number, bytes: number): number;
  _amap_mnn_prepare_input(kind: number, index: number, shape: number, rank: number): number;
  _amap_mnn_input_elements(kind: number, index: number): number;
  _amap_mnn_run(kind: number): number;
  _amap_mnn_output_data(kind: number, index: number): number;
  _amap_mnn_output_elements(kind: number, index: number): number;
  _amap_mnn_unload(kind: number): void;
};

export type AmapModelAssets = {
  encoder: Uint8Array;
  decoder: Uint8Array;
  f0: Uint8Array;
  control: Uint8Array;
};

export type AmapVoiceDictionary = {
  spk_emb: number[];
  spk_vae_emb: number[];
  speed_alpha: number;
  volume_scale: number;
};

/** Parsed output of the APK's text frontend, before the acoustic encoder. */
export type AmapPhonemes = {
  txtTokens: Int32Array;
  tone: Int32Array;
  prosody: Int32Array;
  ph2char: Int32Array;
};

function packTimeChannels(data: Float32Array, frames: number, channels: number): Float32Array {
  const packed = new Float32Array(Math.ceil(frames / 4) * channels * 4);
  for (let frame = 0; frame < frames; frame++)
    for (let channel = 0; channel < channels; channel++)
      packed[(Math.floor(frame / 4) * channels + channel) * 4 + frame % 4] =
        data[frame * channels + channel];
  return packed;
}

export class AmapTtsCore {
  constructor(private readonly mnn: AmapMnnModule, private readonly voice: AmapVoiceDictionary) {
    if (voice.spk_emb.length !== 96 || voice.spk_vae_emb.length !== 96)
      throw new Error('高德音色词典维度不匹配');
  }

  loadModels(models: AmapModelAssets): void {
    const files: Uint8Array[] = [models.encoder, models.decoder, models.f0, models.control];
    for (let kind = 0; kind < files.length; kind++) {
      const file = files[kind];
      const address = this.mnn._malloc(file.byteLength);
      if (!address) throw new Error('高德模型内存分配失败');
      try {
        this.mnn.HEAPU8.set(file, address);
        if (!this.mnn._amap_mnn_load(kind, address, file.byteLength))
          throw new Error(`高德模型 ${kind} 加载失败`);
      } finally {
        this.mnn._free(address);
      }
    }
  }

  dispose(): void {
    for (let kind = 0; kind < 4; kind++) this.mnn._amap_mnn_unload(kind);
  }

  private input(kind: ModelKind, index: number, shape: number[], values: Tensor): void {
    const shapeAddress = this.mnn._malloc(shape.length * 4);
    if (!shapeAddress) throw new Error('高德模型维度内存分配失败');
    this.mnn.HEAP32.set(shape, shapeAddress / 4);
    const dataAddress = this.mnn._amap_mnn_prepare_input(kind, index, shapeAddress, shape.length);
    this.mnn._free(shapeAddress);
    if (!dataAddress || this.mnn._amap_mnn_input_elements(kind, index) !== values.length)
      throw new Error(`高德模型 ${kind} 输入 ${index} 维度不匹配`);
    this.mnn.HEAPU8.set(new Uint8Array(values.buffer, values.byteOffset, values.byteLength), dataAddress);
  }

  private outputs(kind: ModelKind, expected: number): Uint8Array[] {
    const count = this.mnn._amap_mnn_run(kind);
    if (count !== expected) throw new Error(`高德模型 ${kind} 推理失败`);
    return Array.from({ length: count }, (_, index) => {
      const address = this.mnn._amap_mnn_output_data(kind, index);
      const elements = this.mnn._amap_mnn_output_elements(kind, index);
      if (!address || elements < 1) throw new Error(`高德模型 ${kind} 输出无效`);
      return this.mnn.HEAPU8.slice(address, address + elements * 4);
    });
  }

  private static floats(bytes: Uint8Array): Float32Array {
    return new Float32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4).slice();
  }

  private static integers(bytes: Uint8Array): Int32Array {
    return new Int32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4).slice();
  }

  /** Runs all four WebAssembly models plus the JavaScript DDSP vocoder for one utterance. */
  synthesize(phonemes: AmapPhonemes): Float32Array {
    const tokens = phonemes.txtTokens.length;
    if (tokens < 3 || [phonemes.tone, phonemes.prosody, phonemes.ph2char]
      .some(item => item.length !== tokens)) throw new Error('高德音素输入维度不匹配');
    const speaker = Float32Array.from(this.voice.spk_emb);
    const speakerVae = new Float32Array(384);
    for (let i = 0; i < 96; i++) speakerVae[i * 4] = this.voice.spk_vae_emb[i];
    this.input(0, 0, [1, tokens], phonemes.txtTokens);
    this.input(0, 1, [1, 1, 96], speaker);
    this.input(0, 2, [1, 1, 96], speakerVae);
    this.input(0, 3, [1, tokens], phonemes.tone);
    this.input(0, 4, [1, tokens], phonemes.prosody);
    this.input(0, 5, [1, tokens], phonemes.ph2char);
    this.input(0, 6, [1, tokens, 96], new Float32Array(tokens * 96));
    this.input(0, 7, [1, 8, tokens], new Float32Array(tokens * 8));
    const encoded = this.outputs(0, 3);
    const decodedInput = amapExpandAcoustic({
      roundedDurations: AmapTtsCore.integers(encoded[0]),
      latent: AmapTtsCore.floats(encoded[1]),
      linguistic: AmapTtsCore.floats(encoded[2]),
    }, speaker, this.voice.speed_alpha);
    const { frames } = decodedInput;
    this.input(1, 0, [1, frames, 96], decodedInput.linguistic);
    this.input(1, 1, [1, frames, 96], decodedInput.durationEmbedding);
    this.input(1, 2, [1, frames, 96], decodedInput.speaker);
    this.input(1, 3, [1, frames, 96], decodedInput.environment);
    this.input(1, 4, [1, frames, 96], decodedInput.latent);
    const mel = AmapTtsCore.floats(this.outputs(1, 1)[0]);
    if (mel.length !== frames * 160) throw new Error('高德频谱输出维度不匹配');
    // The decoder carries six frames of context on each side of the utterance.
    const audibleFrames = frames - 12;
    if (audibleFrames < 1) throw new Error('高德频谱时长不足');
    const audibleMel = mel.slice(6 * 160, (frames - 6) * 160);
    const spec = packTimeChannels(audibleMel, audibleFrames, 160);
    this.input(2, 0, [1, audibleFrames, 160], spec);
    const f0Output = this.outputs(2, 2);
    const f0Samples = AmapTtsCore.floats(f0Output[0]);
    const f0Frames = AmapTtsCore.floats(f0Output[1]);
    const phase = amapVocoderPhase(f0Samples);
    this.input(3, 0, [1, audibleFrames, 160], spec);
    this.input(3, 1, [1, 1, audibleFrames], f0Frames);
    this.input(3, 2, [1, audibleFrames, 1], phase.phaseFrames);
    const control = this.outputs(3, 4).map(AmapTtsCore.floats);
    const pcm = amapVocoderDsp({
      hMag: control[0], hPhase: control[1], nMag: control[2], nPhase: control[3],
      phaseSamples: phase.phaseSamples, f0Samples,
    });
    return pcm;
  }
}
