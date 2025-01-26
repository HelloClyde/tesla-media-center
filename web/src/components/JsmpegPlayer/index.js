/**
 * According to jsmpeg project(https://github.com/phoboslab/jsmpeg)
 */

// ES6 modular
import Player from './lib/player';
import BitBuffer from './lib/buffer';
import AjaxSource from './lib/ajax';
import FetchSource from './lib/fetch';
import AjaxProgressiveSource from './lib/ajax-progressive';
import WSSource from './lib/websocket';
import TS from './lib/ts';
import BaseDecoder from './lib/decoder';
import MPEG1 from './lib/mpeg1';
import MPEG1WASM from './lib/mpeg1-wasm';
import MP2 from './lib/mp2';
import MP2WASM from './lib/mp2-wasm';
import WebGLRenderer from './lib/webgl';
import CanvasRenderer from './lib/canvas2d';
import WebAudioOut from './lib/webaudio';
import {
  Now, Fill, Base64ToArrayBuffer,
} from './utils';
import WASMModule from './lib/wasm-module';
import WASM_BINARY from './lib/wasm/WASM_BINARY';

// This sets up the JSMpeg "Namespace". The object is empty apart from the Now()
// utility function and the automatic CreateVideoElements() after DOMReady.
const JSMpeg = {
  // The Player sets up the connections between source, demuxer, decoders,
  // renderer and audio output. It ties everything together, is responsible
  // of scheduling decoding and provides some convenience methods for
  // external users.
  Player,

  // The BitBuffer wraps a Uint8Array and allows reading an arbitrary number
  // of bits at a time. On writing, the BitBuffer either expands its
  // internal buffer (for static files) or deletes old data (for streaming).
  BitBuffer,

  // A Source provides raw data from HTTP, a WebSocket connection or any
  // other mean. Sources must support the following API:
  //   .connect(destinationNode)
  //   .write(buffer)
  //   .start() - start reading
  //   .resume(headroom) - continue reading; headroom to play pos in seconds
  //   .established - boolean, true after connection is established
  //   .completed - boolean, true if the source is completely loaded
  //   .progress - float 0-1
  Source: {
    Ajax: AjaxSource,
    AjaxProgressive: AjaxProgressiveSource,
    WebSocket: WSSource,
    Fetch: FetchSource,
  },

  // A Demuxer may sit between a Source and a Decoder. It separates the
  // incoming raw data into Video, Audio and other Streams. API:
  //   .connect(streamId, destinationNode)
  //   .write(buffer)
  //   .currentTime – float, in seconds
  //   .startTime - float, in seconds
  Demuxer: {
    TS,
  },

  // A Decoder accepts an incoming Stream of raw Audio or Video data, buffers
  // it and upon `.decode()` decodes a single frame of data. Video decoders
  // call `destinationNode.render(Y, Cr, CB)` with the decoded pixel data;
  // Audio decoders call `destinationNode.play(left, right)` with the decoded
  // PCM data. API:
  //   .connect(destinationNode)
  //   .write(pts, buffer)
  //   .decode()
  //   .seek(time)
  //   .currentTime - float, in seconds
  //   .startTime - float, in seconds
  Decoder: {
    Base: BaseDecoder,
    MPEG1Video: MPEG1,
    MPEG1VideoWASM: MPEG1WASM,
    MP2Audio: MP2,
    MP2AudioWASM: MP2WASM,
  },

  // A Renderer accepts raw YCrCb data in 3 separate buffers via the render()
  // method. Renderers typically convert the data into the RGBA color space
  // and draw it on a Canvas, but other output - such as writing PNGs - would
  // be conceivable. API:
  //   .render(y, cr, cb) - pixel data as Uint8Arrays
  //   .enabled - wether the renderer does anything upon receiving data
  Renderer: {
    WebGL: WebGLRenderer,
    Canvas2D: CanvasRenderer,
  },

  // Audio Outputs accept raw Stero PCM data in 2 separate buffers via the
  // play() method. Outputs typically play the audio on the user's device.
  // API:
  //   .play(sampleRate, left, right) - rate in herz; PCM data as Uint8Arrays
  //   .stop()
  //   .enqueuedTime - float, in seconds
  //   .enabled - wether the output does anything upon receiving data
  AudioOutput: {
    WebAudio: WebAudioOut,
  },

  WASMModule,

  // functions
  Now,
  Fill,
  Base64ToArrayBuffer,

  // The build process may append `JSMpeg.WASM_BINARY_INLINED = base64data;`
  // to the minified source.
  // If this property is present, jsmpeg will use the inlined binary data
  // instead of trying to load a jsmpeg.wasm file via Ajax.
  WASM_BINARY_INLINED: WASM_BINARY,
};

export default JSMpeg;
