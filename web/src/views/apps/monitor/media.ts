export function captureError(error: unknown) {
  const name = (error as {name?: string})?.name;
  if (name === 'NotAllowedError') return '摄像头或麦克风权限被拒绝，请在浏览器站点设置中允许后重试';
  if (name === 'NotFoundError') return '浏览器未找到摄像头或麦克风，请检查车机是否向网页开放这些设备';
  if (name === 'NotReadableError') return '摄像头或麦克风被其他应用占用，或车机无法读取';
  return error instanceof Error ? error.message : '无法启用摄像头或麦克风';
}
export function requireCaptureSupport() {
  if (!window.isSecureContext) throw Error('请通过 HTTPS 访问 TMC，才能启用摄像头和麦克风（本机 localhost 可用）');
  if (!navigator.mediaDevices?.getUserMedia) throw Error('当前车机浏览器未开放摄像头或麦克风接口');
}

export class MonitorAudio {
  private context: AudioContext;
  private node?: AudioWorkletNode;
  private source?: MediaStreamAudioSourceNode;
  private closed = false;
  private muted = false;
  constructor(private capture: (samples: Uint8Array) => void) {
    this.context = new AudioContext({latencyHint: 'interactive'});
  }
  async start() {
    await this.context.resume();
    if (!this.context.audioWorklet) throw Error('当前浏览器不支持实时对讲音频');
    await this.context.audioWorklet.addModule('/monitor/audio-worklet.js?v=1');
    if (this.closed) return;
    this.node = new AudioWorkletNode(this.context, 'tmc-monitor-audio', {
      numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], channelCount: 1,
    });
    this.node.port.onmessage = event => {
      if (!this.closed && event.data.type === 'pcm') this.capture(new Uint8Array(event.data.buffer));
    };
    this.node.connect(this.context.destination);
  }
  setInput(stream: MediaStream | null) {
    this.source?.disconnect(); this.source = undefined;
    if (stream?.getAudioTracks().length && this.node && !this.closed) {
      this.source = this.context.createMediaStreamSource(stream); this.source.connect(this.node);
    }
  }
  setCapture(enabled: boolean) { this.node?.port.postMessage({type: 'capture', enabled}); }
  setMuted(muted: boolean) { this.muted = muted; this.resetPlayback(); }
  resetPlayback() { this.node?.port.postMessage({type: 'reset'}); }
  play(samples: Uint8Array) {
    if (this.closed || this.muted || samples.byteLength !== 1280) return;
    const buffer = samples.slice().buffer;
    this.node?.port.postMessage({type: 'audio', buffer}, [buffer]);
  }
  async resume() { if (!this.closed) await this.context.resume(); }
  stop() {
    this.closed = true; this.source?.disconnect(); this.node?.disconnect();
    this.node?.port.close(); void this.context.close();
  }
}

export class CameraFrames {
  private video = document.createElement('video');
  private canvas = document.createElement('canvas');
  private timer?: ReturnType<typeof setTimeout>;
  private stopped = false;
  wanted = false;
  constructor(stream: MediaStream, private send: (data: Uint8Array) => void, private width: number) {
    this.video.srcObject = stream; this.video.muted = true; this.video.playsInline = true;
  }
  async start() { await this.video.play(); if (!this.stopped) this.tick(); }
  private tick() {
    if (this.stopped) return;
    if (!this.wanted || this.video.readyState < 2 || !this.video.videoWidth) {
      this.timer = setTimeout(() => this.tick(), 200); return;
    }
    const scale = Math.min(1, this.width / this.video.videoWidth, this.width * 9 / 16 / this.video.videoHeight);
    const width = Math.round(this.video.videoWidth * scale), height = Math.round(this.video.videoHeight * scale);
    if (this.canvas.width !== width || this.canvas.height !== height) { this.canvas.width = width; this.canvas.height = height; }
    this.canvas.getContext('2d', {alpha: false})!.drawImage(this.video, 0, 0, width, height);
    this.canvas.toBlob(async blob => {
      try {
        if (blob && !this.stopped && this.wanted) {
          const data = new Uint8Array(await blob.arrayBuffer());
          if (!this.stopped && this.wanted) this.send(data);
        }
      } finally { if (!this.stopped) this.timer = setTimeout(() => this.tick(), 100); }
    }, 'image/jpeg', .62);
  }
  stop() { this.stopped = true; clearTimeout(this.timer); this.video.pause(); this.video.srcObject = null; }
}

export class FrameRenderer {
  private canvas: HTMLCanvasElement | null = null;
  private pending?: Uint8Array;
  private busy = false;
  private generation = 0;
  constructor(private drawn: () => void) {}
  setCanvas(canvas: HTMLCanvasElement | null) { this.canvas = canvas; void this.draw(); }
  offer(data: Uint8Array) { this.pending = data; void this.draw(); }
  private async draw() {
    if (this.busy || !this.pending || !this.canvas) return;
    const data = this.pending; this.pending = undefined; this.busy = true;
    const generation = this.generation;
    let bitmap: ImageBitmap | undefined;
    try {
      bitmap = await createImageBitmap(new Blob([data.slice().buffer], {type: 'image/jpeg'}));
      const canvas = this.canvas;
      if (!canvas || generation !== this.generation) return;
      if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) { canvas.width = bitmap.width; canvas.height = bitmap.height; }
      canvas.getContext('2d', {alpha: false})!.drawImage(bitmap, 0, 0);
      this.drawn();
    } catch { /* A damaged frame is skipped; subsequent live frames can recover. */ }
    finally { bitmap?.close(); this.busy = false; if (this.pending) void this.draw(); }
  }
  clear() { ++this.generation; this.pending = undefined; this.canvas?.getContext('2d')?.clearRect(0, 0, this.canvas.width, this.canvas.height); }
}
