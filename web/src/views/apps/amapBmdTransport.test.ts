import { expect, it, vi } from 'vitest';
import { decodeBmdOnMainThread, InvalidBmdResponseError, parseBmdBatch, postMapTiles, rawBmdDecodeUnsupported, rawBmdUnsupported, TransientBmdDecodeError, transferableBmdBuffers } from './amapBmdTransport';
import type { decodeMapTile } from './amapBmdDecode';

const { post } = vi.hoisted(() => ({post:vi.fn()}));
vi.mock('axios', () => ({default:{post}}));

function batch() {
  const manifest = {version:1,paints:{day:{}},tiles:[{level:14,x:1,y:2,
    roadPaints:{day:{}},bmd:{collectionBmd:[0,3],surfacesBmd:[3,2]}}]};
  const header = new TextEncoder().encode(JSON.stringify(manifest)), body = new Uint8Array([1,2,3,4,5]);
  const result = new Uint8Array(12+header.length+body.length);
  result.set(new TextEncoder().encode('TMCBMD1!'));
  new DataView(result.buffer).setUint32(8,header.length,true);
  result.set(header,12); result.set(body,12+header.length);
  return result;
}

it('reads bounded binary BMD spans and passes native bytes to the browser decoder', () => {
  const parsed = parseBmdBatch(batch());
  expect(Array.from(parsed.tiles[0].collectionBmd as Uint8Array)).toEqual([1,2,3]);
  expect(Array.from(parsed.tiles[0].surfacesBmd as Uint8Array)).toEqual([4,5]);
  expect(parsed.tiles[0].roadPaints).toEqual({day:{}});
  const transfer=transferableBmdBuffers(parsed.tiles);
  expect(transfer).toEqual([(parsed.tiles[0].collectionBmd as Uint8Array).buffer]);
  const cloned=structuredClone(parsed.tiles,{transfer});
  expect(Array.from(cloned[0].collectionBmd as Uint8Array)).toEqual([1,2,3]);
  expect(transfer[0].byteLength).toBe(0);
  const truncated = batch().subarray(0,-1);
  expect(() => parseBmdBatch(truncated)).toThrow('invalid BMD span');
});

it('accepts binary success and JSON pending or login responses', async () => {
  post.mockResolvedValueOnce({status:200,data:batch().buffer});
  const ready = await postMapTiles('/api/amap-app/map/bmd',{level:14,tiles:[[1,2]]});
  expect(ready.data.status).toBe('ok');
  expect(ready.data.data.tiles[0].collectionBmd).toBeInstanceOf(Uint8Array);
  expect(post.mock.calls[0][2].headers.Accept).toBe('application/vnd.tmc.amap-bmd');
  post.mockResolvedValueOnce({status:200,data:batch().buffer});
  const prefetched = await postMapTiles('/api/amap-app/map/bmd/prefetch',{level:14,tiles:[[1,2]]});
  expect(prefetched.data.data.tiles[0].surfacesBmd).toBeInstanceOf(Uint8Array);
  expect(post.mock.calls[1][2].headers.Accept).toBe('application/vnd.tmc.amap-bmd');
  post.mockResolvedValueOnce({status:202,data:new ArrayBuffer(0)});
  const pending = await postMapTiles('/api/amap-app/map/bmd/prefetch',{level:14,tiles:[[1,2]]});
  expect(pending.status).toBe(202);
  expect(pending.data).toBeUndefined();
  for (const payload of [{status:'ok',data:{pending:true}},{status:'need_login'}]) {
    post.mockResolvedValueOnce({status:payload.data?.pending ? 202 : 200,
      data:new TextEncoder().encode(JSON.stringify(payload)).buffer});
    expect((await postMapTiles('/api/amap-app/map/bmd',{level:14,tiles:[[1,2]]})).data).toEqual(payload);
  }
});

it('falls back only for unavailable or malformed BMD transport, not temporary failures', () => {
  expect(rawBmdUnsupported({response:{status:404}})).toBe(true);
  expect(rawBmdUnsupported({response:{status:415}})).toBe(true);
  expect(rawBmdUnsupported(new InvalidBmdResponseError('invalid'))).toBe(true);
  for (const status of [401,429,500,502,503])
    expect(rawBmdUnsupported({response:{status}})).toBe(false);
  expect(rawBmdUnsupported(new Error('network timeout'))).toBe(false);
  expect(rawBmdDecodeUnsupported(new TransientBmdDecodeError('worker timeout'))).toBe(false);
  expect(rawBmdDecodeUnsupported(new Error('invalid BMD section'))).toBe(true);
});

it('decodes an empty raw tile without a Worker and preserves an older decoded response', () => {
  const raw=decodeBmdOnMainThread([{level:14,x:1,y:2}],{})[0] as ReturnType<typeof decodeMapTile>;
  expect(raw.collection).toEqual({type:'FeatureCollection',features:[]});
  expect(raw.surfaces).toEqual([]);
  const legacy={level:14,x:1,y:2,collection:{type:'FeatureCollection',features:[{id:1}]}};
  expect(decodeBmdOnMainThread([legacy],{})[0]).toBe(legacy);
});
