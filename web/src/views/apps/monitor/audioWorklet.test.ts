import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';
import { expect, it, vi } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'public/monitor/audio-worklet.js'), 'utf8');
function processor(rate: number) {
  let Processor: any;
  runInNewContext(source, {sampleRate: rate, Int16Array, Float32Array,
    AudioWorkletProcessor: class {port = {postMessage: vi.fn(), onmessage: undefined};},
    registerProcessor: (_name: string, value: any) => { Processor = value; },
  });
  return new Processor();
}
it.each([44100, 48000])('captures exactly 16 kHz speech at an input sample rate of %s without local echo', rate => {
  const node = processor(rate); node.port.onmessage({data: {type: 'capture', enabled: true}});
  let remaining = rate;
  while (remaining) {
    const size = Math.min(128, remaining), output = new Float32Array(size);
    node.process([[new Float32Array(size).fill(.25)]], [[output]]);
    expect(output.every(sample => sample === 0)).toBe(true); remaining -= size;
  }
  const messages = node.port.postMessage.mock.calls;
  expect(messages).toHaveLength(25);
  const samples = new Int16Array(messages[0][0].buffer);
  expect(samples).toHaveLength(640); expect(samples.every(sample => sample === 8192)).toBe(true);
  node.port.onmessage({data: {type: 'capture', enabled: false}});
  node.process([[new Float32Array(128)]], [[new Float32Array(128)]]);
  expect(node.port.postMessage).toHaveBeenCalledTimes(25);
});
it('bounds audio delay, starts after buffering and clears old sound on disconnect', () => {
  const node = processor(48000);
  const add = (value: number) => node.port.onmessage({data: {type: 'audio', buffer: new Int16Array(640).fill(value).buffer}});
  add(8000);
  const output = new Float32Array(128);
  node.process([], [[output]]); expect(output.every(sample => sample === 0)).toBe(true);
  add(8000); node.process([], [[output]]); expect(output.every(sample => sample > .2)).toBe(true);
  for (let i = 0; i < 30; i++) add(2000);
  expect(node.length).toBeLessThanOrEqual(3840);
  node.port.onmessage({data: {type: 'reset'}}); node.process([], [[output]]);
  expect(output.every(sample => sample === 0)).toBe(true); expect(node.length).toBe(0);
});
