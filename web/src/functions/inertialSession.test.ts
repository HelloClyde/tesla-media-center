import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createInertialSession } from './inertialSession';
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
const ok = (data: unknown) => new Response(JSON.stringify({ status: 'ok', data }), { status: 200 });
const sample = (timestamp: number) => ({ timestamp, gyro: [0, 0, 0], acceleration: [0, 0, 9.8] });
const ack = (timestamp: number, sequence = 0) => ok({ sequence, result: { state: 2, output: null, accepted: 1, timestamp } });

it('negotiates browser input and acknowledges its converted relative clock', async () => {
  const request = vi.fn().mockResolvedValueOnce(ok({ id: 'browser', nextSequence: 0, format: 'browser' }))
    .mockResolvedValueOnce(ack(21)).mockResolvedValue(ok({ closed: true }));
  const output = vi.fn(), error = vi.fn();
  const client = createInertialSession(output, error, request, 'browser');
  expect(await client.start()).toBe(true);
  const reading = { elapsed: 20.5, angularVelocity: [1,2,3], acceleration: [4,5,6] };
  client.push(reading); reading.angularVelocity[0] = 999;
  await vi.advanceTimersByTimeAsync(200);
  expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ format: 'browser' });
  expect(JSON.parse(request.mock.calls[1][1].body).samples[0].angularVelocity[0]).toBe(1);
  expect(output).toHaveBeenCalledOnce(); expect(error).not.toHaveBeenCalled();
  client.stop(); await vi.runAllTimersAsync();
});

it('retries identical bytes and preserves input snapshots and batch order', async () => {
  const request = vi.fn().mockResolvedValueOnce(ok({ id: 'one', nextSequence: 0 }))
    .mockRejectedValueOnce(new TypeError('lost response')).mockResolvedValueOnce(ack(1))
    .mockResolvedValueOnce(ack(2, 1)).mockResolvedValue(ok({ closed: true }));
  const output = vi.fn(), error = vi.fn();
  const client = createInertialSession(output, error, request);
  expect(await client.start()).toBe(true);
  const input = sample(1); client.push(input); input.gyro[0] = 999;
  await vi.advanceTimersByTimeAsync(200);
  expect(request.mock.calls[1][1].body).toBe(request.mock.calls[2][1].body);
  expect(JSON.parse(request.mock.calls[1][1].body).samples[0].gyro[0]).toBe(0);
  client.push(sample(2)); await vi.advanceTimersByTimeAsync(200);
  expect(output).toHaveBeenCalledTimes(2); expect(error).not.toHaveBeenCalled();
  expect(JSON.parse(request.mock.calls[3][1].body).sequence).toBe(1);
  client.stop(); await vi.runAllTimersAsync();
});

it('discards late output after stop and closes after an in-flight batch', async () => {
  let resolve!: (value: Response) => void;
  const request = vi.fn().mockResolvedValueOnce(ok({ id: 'one', nextSequence: 0 }))
    .mockImplementationOnce(() => new Promise<Response>(r => { resolve = r; }))
    .mockResolvedValue(ok({ closed: true }));
  const output = vi.fn(), client = createInertialSession(output, vi.fn(), request);
  await client.start(); client.push(sample(1)); await vi.advanceTimersByTimeAsync(200);
  client.stop(); expect(request).toHaveBeenCalledTimes(2);
  resolve(ack(1)); await vi.advanceTimersByTimeAsync(0);
  expect(output).not.toHaveBeenCalled();
  expect(request.mock.calls[2][1].method).toBe('DELETE');
  expect(client.push(sample(2))).toBe(false);
});

it('closes a session that finishes creation after cancellation', async () => {
  let resolve!: (value: Response) => void;
  const request = vi.fn().mockImplementationOnce(() => new Promise<Response>(r => { resolve = r; }))
    .mockResolvedValue(ok({ closed: true }));
  const client = createInertialSession(vi.fn(), vi.fn(), request);
  const opening = client.start(); client.stop(); resolve(ok({ id: 'late', nextSequence: 0 }));
  expect(await opening).toBe(false);
  expect(request.mock.calls[1][0]).toContain('/late');
  await vi.runAllTimersAsync();
});

it('stops on queue overflow instead of silently dropping sensor samples', async () => {
  const request = vi.fn().mockResolvedValueOnce(ok({ id: 'one', nextSequence: 0 }))
    .mockResolvedValue(ok({ closed: true }));
  const error = vi.fn(), client = createInertialSession(vi.fn(), error, request);
  await client.start();
  for (let n = 1; n <= 250; n++) expect(client.push(sample(n))).toBe(true);
  expect(client.push(sample(251))).toBe(false);
  expect(error).toHaveBeenCalledOnce(); await vi.runAllTimersAsync();
  expect(request.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
});

it('rejects invalid engine coordinates before publication', async () => {
  const request = vi.fn().mockResolvedValueOnce(ok({ id: 'one', nextSequence: 0 }))
    .mockResolvedValueOnce(ok({ sequence: 0, result: { state: 8, timestamp: 1, accepted: 1,
      output: { timestamp: 1, longitude: 181, latitude: 30, altitude: 0, quality: 1,
        state: 8, missing_fix: false, source: 'amap-vdr-ordinary' } } }))
    .mockResolvedValue(ok({ closed: true }));
  const output = vi.fn(), error = vi.fn(), client = createInertialSession(output, error, request);
  await client.start(); client.push(sample(1)); await vi.advanceTimersByTimeAsync(200);
  expect(output).not.toHaveBeenCalled(); expect(error).toHaveBeenCalledOnce();
  await vi.runAllTimersAsync();
});
