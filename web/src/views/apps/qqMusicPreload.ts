export interface PlaybackSources { url: string; urls?: string[] }
type WarmAudio = Pick<HTMLAudioElement, 'preload' | 'muted' | 'crossOrigin' | 'src' | 'load' | 'pause' | 'removeAttribute'>;

/** One silent, best-effort browser media-cache warmup; never calls play(). */
export class NextTrackPreload {
  private job?: { key: string; started: number; cancelled: boolean; audio?: WarmAudio;
    result: Promise<PlaybackSources | undefined> };

  constructor(private createAudio: () => WarmAudio = () => new Audio(),
              private now: () => number = Date.now) {}

  prepare(key: string, resolve: () => Promise<PlaybackSources>, cors: boolean) {
    if (this.job?.key === key) return;
    this.clear();
    const job = { key, started: this.now(), cancelled: false, audio: undefined as WarmAudio | undefined,
      result: Promise.resolve(undefined) as Promise<PlaybackSources | undefined> };
    this.job = job;
    job.result = Promise.resolve().then(resolve).then(result => {
      if (job.cancelled) return undefined;
      const url = result.urls?.[0] || result.url;
      if (!url) return undefined;
      try {
        const audio = this.createAudio();
        job.audio = audio;
        audio.preload = 'auto';
        audio.muted = true;
        if (cors) audio.crossOrigin = 'anonymous';
        audio.src = url;
        audio.load();
      } catch { /* URL resolution is useful even if the browser declines warmup. */ }
      return result;
    }).catch(() => undefined);
  }

  take(key: string) {
    const job = this.job;
    if (!job || job.key !== key || this.now() - job.started > 120_000) {
      this.clear();
      return undefined;
    }
    // The foreground player owns this lease until it starts or fails.
    this.job = undefined;
    return { result: job.result, release: () => this.dispose(job) };
  }

  clear() {
    if (this.job) this.dispose(this.job);
    this.job = undefined;
  }

  private dispose(job: NonNullable<NextTrackPreload['job']>) {
    job.cancelled = true;
    if (job.audio) {
      job.audio.pause();
      job.audio.removeAttribute('src');
      job.audio.load();
      job.audio = undefined;
    }
  }
}
