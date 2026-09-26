export type Room = 'room' | 'hall';
// Stereo room response: decorrelated decaying tails and discrete early reflections.
export function roomImpulse(sampleRate: number, room: Room): [Float32Array, Float32Array] {
  if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 192000) throw new Error('Invalid sample rate');
  const seconds = room === 'hall' ? 1.6 : .55;
  const size = Math.ceil(sampleRate * seconds);
  return [0, 1].map(channel => {
    const data = new Float32Array(size);
    let seed = 1927 + channel * 917;
    const delay = Math.floor(sampleRate * (room === 'hall' ? .025 : .012));
    for (let i = delay; i < size; i++) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      const t = (i - delay) / (size - delay);
      data[i] = ((seed / 4294967296) * 2 - 1) * Math.exp(-7 * t) * (1 - t) * .12;
    }
    for (const [index, reflection] of [.019, .037, .061].entries()) {
      const at = Math.floor(sampleRate * (reflection * (room === 'hall' ? 1.8 : 1) + channel * .003));
      data[at] += .6 / (index + 1);
    }
    return data;
  }) as [Float32Array, Float32Array];
}

export function outputCandidates(max: number, surround: boolean): number[] {
  return surround ? [8, 6, 2].filter(count => count === 2 || count <= max) : [2];
}
// Upmix stereo music: dry front pair, restrained mono center/LFE, wet surround pairs.
// This is synthesized surround, not decoding an original Dolby/QQ multichannel master.
export function routeSpatialOutput(ctx: AudioContext, dry: AudioNode, wet: AudioNode, surround: boolean) {
  for (const count of outputCandidates(ctx.destination.maxChannelCount, surround)) {
    const nodes: AudioNode[] = [];
    dry.disconnect(); wet.disconnect();
    try {
      ctx.destination.channelCount = count;
      ctx.destination.channelInterpretation = 'discrete';
      if (ctx.destination.channelCount !== count) throw new Error('Output layout rejected');
      if (count === 2) { dry.connect(ctx.destination); wet.connect(ctx.destination); }
      else {
        const front = ctx.createChannelSplitter(2), ambience = ctx.createChannelSplitter(2), merge = ctx.createChannelMerger(count);
        nodes.push(front, ambience, merge);
        dry.connect(front); wet.connect(ambience);
        const send = (source: AudioNode, output: number, target: number, amount: number, delay = 0) => {
          const gain = ctx.createGain(); nodes.push(gain); gain.gain.value = amount;
          source.connect(gain, output);
          if (delay) { const echo = ctx.createDelay(.1); nodes.push(echo); echo.delayTime.value = delay; gain.connect(echo); echo.connect(merge, 0, target); }
          else gain.connect(merge, 0, target);
        };
        send(front, 0, 0, 1); send(front, 1, 1, 1);
        send(front, 0, 2, .25); send(front, 1, 2, .25);
        const bass = ctx.createBiquadFilter(); nodes.push(bass); bass.type = 'lowpass'; bass.frequency.value = 120; bass.Q.value = .707;
        const mono = ctx.createGain(); nodes.push(mono); mono.channelCount = 1; mono.channelCountMode = 'explicit'; mono.gain.value = .25;
        dry.connect(mono); mono.connect(bass); bass.connect(merge, 0, 3);
        send(ambience, 0, 4, .8); send(ambience, 1, 5, .8);
        if (count === 8) { send(ambience, 0, 6, .55, .018); send(ambience, 1, 7, .55, .024); }
        merge.connect(ctx.destination);
      }
      return { channels: count, dispose: () => { dry.disconnect(); wet.disconnect(); nodes.forEach(node => node.disconnect()); } };
    } catch {
      dry.disconnect(); wet.disconnect(); nodes.forEach(node => node.disconnect());
    }
  }
  throw new Error('Audio output unavailable');
}
