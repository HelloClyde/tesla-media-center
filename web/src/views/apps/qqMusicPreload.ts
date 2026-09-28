export interface PlaybackSources { url: string; urls?: string[] }
export async function warmMediaRequest(url: string, signal: AbortSignal) {
  const limit = 256 * 1024;
  const response = await fetch(url, { signal, headers: { Range: `bytes=0-${limit - 1}` } });
  if (!response.ok || !response.body) { await response.body?.cancel(); return; }
  const reader = response.body.getReader();
  try {
    let received = 0;
    while (received < limit) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
    }
  } finally { await reader.cancel(); }
}

/** Resolve the next URL and warm HTTP caches without creating a media element.
 * CDN CORS/cache policy may prevent warming; resolved URLs remain reusable. */
export class NextTrackPreload {
  private job?: { key: string; started: number; cancelled: boolean; controller?: AbortController;
    timer?: ReturnType<typeof setTimeout>;
    result: Promise<PlaybackSources | undefined> };

  constructor(private warm: (url: string, signal: AbortSignal) => Promise<void> = warmMediaRequest,
              private now: () => number = Date.now) {}

  prepare(key: string, resolve: () => Promise<PlaybackSources>) {
    if (this.job?.key === key) return;
    this.clear();
    const job = { key, started: this.now(), cancelled: false, controller: undefined as AbortController | undefined,
      timer: undefined as ReturnType<typeof setTimeout> | undefined,
      result: Promise.resolve(undefined) as Promise<PlaybackSources | undefined> };
    this.job = job;
    job.result = Promise.resolve().then(resolve).then(result => {
      if (job.cancelled) return undefined;
      const url = result.urls?.[0] || result.url;
      if (!url) return undefined;
      try {
        const controller = new AbortController(); job.controller = controller;
        job.timer = setTimeout(() => controller.abort(), 10000);
        void this.warm(url, controller.signal).catch(() => {}).finally(() => clearTimeout(job.timer));
      } catch { clearTimeout(job.timer); /* Keep URL resolution even if warming fails. */ }
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
    clearTimeout(job.timer);
    job.controller?.abort();
    job.controller = undefined;
  }
}
