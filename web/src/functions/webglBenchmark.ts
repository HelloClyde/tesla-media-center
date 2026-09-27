export interface ComputeResult { size: number; milliseconds: number; gflops: number; gpuMilliseconds?: number; gpuGflops?: number; maxError: number; samples: number }
export const matrixA = (row: number, col: number) => ((row * 3 + col * 7) % 17 - 8) / 16;
export const matrixB = (row: number, col: number) => ((row * 5 + col * 2) % 13 - 6) / 16;
export function referenceCell(n: number, row: number, col: number) {
  let sum = 0;
  for (let k = 0; k < n; k++) sum += matrixA(row, k) * matrixB(k, col);
  return sum;
}

export class WebGLBenchmark {
  readonly canvas = document.createElement('canvas');
  readonly gl: WebGL2RenderingContext;
  private stopped = false;
  constructor() {
    const gl = this.canvas.getContext('webgl2', { antialias: false, depth: false, stencil: false });
    if (!gl) throw Error('当前浏览器未开放 WebGL 2，无法运行此计算测试');
    this.gl = gl;
    this.canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); this.stopped = true; });
  }
  info() {
    const g = this.gl, debug = g.getExtension('WEBGL_debug_renderer_info');
    return {
      renderer: String(g.getParameter(debug ? debug.UNMASKED_RENDERER_WEBGL : g.RENDERER)),
      vendor: String(g.getParameter(debug ? debug.UNMASKED_VENDOR_WEBGL : g.VENDOR)),
      version: String(g.getParameter(g.VERSION)),
      floatTarget: !!g.getExtension('EXT_color_buffer_float'),
      maxTexture: g.getParameter(g.MAX_TEXTURE_SIZE) as number,
      textureUnits: g.getParameter(g.MAX_TEXTURE_IMAGE_UNITS) as number,
      precision: g.getShaderPrecisionFormat(g.FRAGMENT_SHADER, g.HIGH_FLOAT)?.precision || 0,
      webgpu: 'gpu' in navigator,
      gpuTimer: !!g.getExtension('EXT_disjoint_timer_query_webgl2'),
    };
  }
  private check() {
    if (this.stopped || this.gl.isContextLost()) throw Error('测试已停止或 GPU 上下文已丢失');
    const error = this.gl.getError();
    if (error !== this.gl.NO_ERROR) throw Error('WebGL 错误 0x' + error.toString(16));
  }
  private async wait() {
    const g = this.gl, fence = g.fenceSync(g.SYNC_GPU_COMMANDS_COMPLETE, 0);
    if (!fence) throw Error('无法创建 GPU 同步对象');
    g.flush(); const start = performance.now();
    try {
      while (true) {
        // Yield to the browser before querying the fence, so commands can complete.
        await new Promise(resolve => setTimeout(resolve, 0)); this.check();
        const status = g.clientWaitSync(fence, 0, 0);
        if (status === g.ALREADY_SIGNALED || status === g.CONDITION_SATISFIED) return;
        if (status === g.WAIT_FAILED) throw Error('等待 GPU 计算失败');
        if (performance.now() - start > 10000) throw Error('GPU 响应超过 10 秒，已停止测试');
      }
    } finally { g.deleteSync(fence); }
  }
  private texture(width: number, height: number, data?: Float32Array) {
    const g = this.gl, texture = g.createTexture();
    if (!texture) throw Error('无法分配纹理');
    g.bindTexture(g.TEXTURE_2D, texture);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MIN_FILTER, g.NEAREST);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MAG_FILTER, g.NEAREST);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_S, g.CLAMP_TO_EDGE);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_T, g.CLAMP_TO_EDGE);
    g.texImage2D(g.TEXTURE_2D, 0, g.RGBA32F, width, height, 0, g.RGBA, g.FLOAT, data || null);
    return texture;
  }
  async compute(n: number): Promise<ComputeResult> {
    if (![64, 128, 256, 512].includes(n)) throw Error('不支持的矩阵尺寸');
    const g = this.gl;
    if (!g.getExtension('EXT_color_buffer_float')) throw Error('缺少浮点渲染支持，无法执行 FP32 矩阵测试');
    const textures: WebGLTexture[] = [], shaders: WebGLShader[] = [];
    const program = g.createProgram(), framebuffer = g.createFramebuffer();
    if (!program || !framebuffer) throw Error('GPU 资源创建失败');
    try {
      const source = [
        `#version 300 es
        void main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));gl_Position=vec4(p*2.0-1.0,0,1);}`,
        `#version 300 es
        precision highp float; precision highp int;
        uniform highp sampler2D a; uniform highp sampler2D b; out vec4 result;
        void main(){ivec2 p=ivec2(gl_FragCoord.xy);float sum=0.0;
        for(int k=0;k<${n};k++){sum+=texelFetch(a,ivec2(k,p.y),0).r*texelFetch(b,ivec2(p.x,k),0).r;}
        result=vec4(sum,0,0,1);}`,
      ];
      for (let i = 0; i < 2; i++) {
        const shader = g.createShader(i ? g.FRAGMENT_SHADER : g.VERTEX_SHADER);
        if (!shader) throw Error('着色器创建失败');
        shaders.push(shader); g.shaderSource(shader, source[i]); g.compileShader(shader);
        if (!g.getShaderParameter(shader, g.COMPILE_STATUS)) throw Error('着色器编译失败：' + g.getShaderInfoLog(shader));
        g.attachShader(program, shader);
      }
      g.linkProgram(program);
      if (!g.getProgramParameter(program, g.LINK_STATUS)) throw Error('计算程序链接失败：' + g.getProgramInfoLog(program));
      g.useProgram(program);
      for (const [i, value] of [matrixA, matrixB].entries()) {
        const data = new Float32Array(n * n * 4);
        for (let row = 0; row < n; row++) for (let col = 0; col < n; col++) data[(row * n + col) * 4] = value(row, col);
        g.activeTexture(g.TEXTURE0 + i); textures.push(this.texture(n, n, data));
        g.uniform1i(g.getUniformLocation(program, i ? 'b' : 'a'), i);
      }
      g.activeTexture(g.TEXTURE2); const output = this.texture(n, n); textures.push(output);
      g.bindFramebuffer(g.FRAMEBUFFER, framebuffer);
      g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, output, 0);
      if (g.checkFramebufferStatus(g.FRAMEBUFFER) !== g.FRAMEBUFFER_COMPLETE) throw Error('浮点帧缓冲不可用');
      g.viewport(0, 0, n, n); g.disable(g.DITHER); g.disable(g.BLEND);
      const draw = async () => { this.check(); g.drawArrays(g.TRIANGLES, 0, 3); await this.wait(); };
      await draw(); // Warm-up excludes compilation and first submission from timing.
      const times: number[] = [], gpuTimes: number[] = [];
      const timer = g.getExtension('EXT_disjoint_timer_query_webgl2');
      let disjoint = timer ? !!g.getParameter(timer.GPU_DISJOINT_EXT) : true;
      for (let i = 0; i < 5; i++) {
        const query = timer ? g.createQuery() : null;
        try {
          this.check(); const start = performance.now();
          if (query) g.beginQuery(timer.TIME_ELAPSED_EXT, query);
          g.drawArrays(g.TRIANGLES, 0, 3);
          if (query) g.endQuery(timer.TIME_ELAPSED_EXT);
          await this.wait(); times.push(performance.now() - start);
          if (query) {
            disjoint ||= !!g.getParameter(timer.GPU_DISJOINT_EXT);
            if (g.getQueryParameter(query, g.QUERY_RESULT_AVAILABLE)) {
              const ms = Number(g.getQueryParameter(query, g.QUERY_RESULT)) / 1e6;
              if (Number.isFinite(ms) && ms > 0) gpuTimes.push(ms);
            }
          }
        } finally { if (query) g.deleteQuery(query); }
      }
      let maxError = 0;
      for (const [row, col] of [[0, 0], [n - 1, n - 1], [3, 7], [n >> 1, n >> 1]]) {
        const pixel = new Float32Array(4); g.readPixels(col, row, 1, 1, g.RGBA, g.FLOAT, pixel); this.check();
        const error = Math.abs(pixel[0] - referenceCell(n, row, col));
        if (!Number.isFinite(error)) throw Error('GPU 计算产生非有限数值');
        maxError = Math.max(maxError, error);
      }
      if (maxError > 0.001) throw Error('矩阵正确性校验失败，最大误差 ' + maxError);
      const milliseconds = times.sort((a, b) => a - b)[2];
      const gpuMilliseconds = !disjoint && gpuTimes.length === 5 ? gpuTimes.sort((a, b) => a - b)[2] : undefined;
      return { size: n, milliseconds, gflops: 2 * n ** 3 / (milliseconds * 1e6), gpuMilliseconds,
        gpuGflops: gpuMilliseconds ? 2 * n ** 3 / (gpuMilliseconds * 1e6) : undefined, maxError, samples: times.length };
    } finally {
      textures.forEach(t => g.deleteTexture(t)); shaders.forEach(s => g.deleteShader(s));
      g.deleteProgram(program); g.deleteFramebuffer(framebuffer);
    }
  }
  async memory(mib: number, progress: (value: number) => void) {
    if (![16, 32, 64, 128].includes(mib)) throw Error('不支持的分配上限');
    const g = this.gl, textures: WebGLTexture[] = [], framebuffer = g.createFramebuffer();
    if (!framebuffer) throw Error('无法创建纹理测试帧缓冲');
    try {
      g.bindFramebuffer(g.FRAMEBUFFER, framebuffer);
      for (let allocated = 0; allocated < mib; allocated += 4) {
        this.check(); const texture = g.createTexture(); if (!texture) throw Error('纹理分配失败');
        textures.push(texture); g.bindTexture(g.TEXTURE_2D, texture);
        g.texStorage2D(g.TEXTURE_2D, 1, g.RGBA8, 1024, 1024);
        g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, texture, 0);
        if (g.checkFramebufferStatus(g.FRAMEBUFFER) !== g.FRAMEBUFFER_COMPLETE) throw Error('分配测试帧缓冲不可用');
        g.clearColor(0.25, 0.5, 0.75, 1); g.clear(g.COLOR_BUFFER_BIT); await this.wait();
        const pixel = new Uint8Array(4); g.readPixels(0, 0, 1, 1, g.RGBA, g.UNSIGNED_BYTE, pixel); this.check();
        if (Math.abs(pixel[0] - 64) > 1 || pixel[3] !== 255) throw Error('纹理读写校验失败');
        progress(allocated + 4);
      }
    } finally { textures.forEach(t => g.deleteTexture(t)); g.deleteFramebuffer(framebuffer); }
  }
  dispose() { this.stopped = true; this.gl.getExtension('WEBGL_lose_context')?.loseContext(); }
}
