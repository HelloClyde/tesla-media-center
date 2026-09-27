import fs from 'node:fs';
import assert from 'node:assert/strict';
const base=new URL('../../web/public/gam4980/',import.meta.url);
const {instance}=await WebAssembly.instantiate(fs.readFileSync(new URL('core.wasm',base)),{});
const c=instance.exports;
for(const [name,ptr] of [['8.BIN',c.web_rom8()],['E.BIN',c.web_rome()]])new Uint8Array(c.memory.buffer,ptr,0x200000).set(fs.readFileSync(new URL(name,base)));
assert.equal(c.web_init(),1,'ROM boot');
assert.equal(c.web_load(0),-1,'invalid length');
const game=new Uint8Array(0x46+19);game[0x40]=0x46;game[0x41]=0x50;
// Original test program: fill LCD RAM and loop; no copyrighted game fixture.
game.set([0x78,0xa2,0,0x8a,0x9d,0,4,0x9d,0,5,0x9d,0,6,0xe8,0xd0,0xf3,0x4c,0x56,0x50],0x46);
new Uint8Array(c.memory.buffer,c.gam4980_game_storage(),game.length).set(game);
assert.equal(c.web_load(game.length),1);
for(let i=0;i<120;i++)c.gam4980_run_frame();
assert.ok(new Set(new Uint16Array(c.memory.buffer,c.gam4980_framebuffer(),160*96)).size>1,'LCD pixels');
assert.equal(c.gam4980_shutdown_requested(),0);
c.gam4980_key_down(0x2f);
assert.equal(new Uint8Array(c.memory.buffer,c.gam4980_save_data(),0x14000).length,81920);
console.log('ROM boot, invalid game length, 120 frames, LCD output and save buffer passed');
