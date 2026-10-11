// 16 kHz mono speech; capture and playout stay off the map's rendering thread.
class MonitorAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.capture = false;
    this.phase = 0; this.sum = 0; this.count = 0;
    this.captureBuffer = new Int16Array(640); this.captureOffset = 0;
    this.ring = new Float32Array(6400); this.read = 0; this.length = 0;
    this.playing = false; this.playPhase = 0;
    this.port.onmessage = ({data}) => {
      if (data.type === 'capture') {
        this.capture = data.enabled; this.captureOffset = this.phase = this.sum = this.count = 0;
      } else if (data.type === 'reset') {
        this.length = 0; this.playing = false; this.playPhase = 0;
      } else if (data.type === 'audio') {
        const samples = new Int16Array(data.buffer);
        // Keep at most 240 ms. After congestion, resume from recent audio.
        if (this.length + samples.length > 3840) {
          this.read = (this.read + this.length) % this.ring.length;
          this.length = 0; this.playing = false; this.playPhase = 0;
        }
        for (let i = 0; i < samples.length; i++) {
          this.ring[(this.read + this.length++) % this.ring.length] = samples[i] / 32768;
        }
      }
    };
  }
  process(inputs, outputs) {
    const input = inputs[0]?.[0];
    if (this.capture && input) {
      for (let i = 0; i < input.length; i++) {
        this.sum += input[i]; this.count++; this.phase += 16000;
        if (this.phase >= sampleRate) {
          this.phase -= sampleRate;
          const value = Math.max(-1, Math.min(1, this.sum / this.count));
          this.captureBuffer[this.captureOffset++] = Math.round(value * (value < 0 ? 32768 : 32767));
          this.sum = this.count = 0;
          if (this.captureOffset === this.captureBuffer.length) {
            const buffer = this.captureBuffer.buffer;
            this.port.postMessage({type: 'pcm', buffer}, [buffer]);
            this.captureBuffer = new Int16Array(640); this.captureOffset = 0;
          }
        }
      }
    }
    const output = outputs[0]?.[0];
    if (!output) return true;
    output.fill(0);
    if (!this.playing && this.length >= 1280) this.playing = true;
    if (this.playing) {
      for (let i = 0; i < output.length; i++) {
        if (this.length < 2) { this.playing = false; this.playPhase = 0; break; }
        const first = this.ring[this.read], second = this.ring[(this.read + 1) % this.ring.length];
        output[i] = first + (second - first) * this.playPhase;
        this.playPhase += 16000 / sampleRate;
        while (this.playPhase >= 1) {
          this.playPhase--; this.read = (this.read + 1) % this.ring.length; this.length--;
        }
      }
    }
    return true;
  }
}
registerProcessor('tmc-monitor-audio', MonitorAudioProcessor);
