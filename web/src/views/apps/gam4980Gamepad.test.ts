import { describe,it,expect } from 'vitest';
import { gamepadKeys,createGamepadRepeater } from './gam4980Gamepad';
const pad=(pressed:number[]=[],axes=[0,0])=>({buttons:Array.from({length:16},(_,i)=>({pressed:pressed.includes(i),touched:false,value:pressed.includes(i)?1:0})),axes});
describe('GAM gamepad',()=>{
  it('maps standard buttons and deduplicates stick/dpad',()=>{
    expect([...gamepadKeys(pad([0,1,12],[0,-1]))]).toEqual([0x2f,0x2e,0x35]);
    expect(gamepadKeys(pad([],[.3,-.2])).size).toBe(0);
    expect([...gamepadKeys(pad([],[.8,.9]))]).toEqual([0x38]);
  });
  it('repeats directions but not confirm, clears released and disconnected inputs',()=>{
    const r=createGamepadRepeater(),keys=new Set([0x35,0x2f]);
    expect(r.update(keys,0)).toEqual([0x35,0x2f]);
    expect(r.update(keys,300)).toEqual([]);
    expect(r.update(keys,350)).toEqual([0x35]);
    expect(r.update(keys,460)).toEqual([0x35]);
    r.update(new Set(),500);
    expect(r.update(keys,600)).toEqual([0x35,0x2f]);
    r.reset();expect(r.update(keys,700)).toEqual([0x35,0x2f]);
  });
});
