export type PadState = Pick<Gamepad, 'buttons' | 'axes'>;
const buttons: Record<number, number> = {0:0x2f,1:0x2e,2:0x36,3:0x29,4:0x3a,5:0x3b,8:1,12:0x35,13:0x38,14:0x37,15:0x39};
const directions = new Set([0x35,0x38,0x37,0x39]);
export function gamepadKeys(pad: PadState): Set<number> {
  const keys=new Set<number>();
  for(const [index,key] of Object.entries(buttons)) if(pad.buttons[Number(index)]?.pressed)keys.add(key);
  const x=pad.axes[0]||0,y=pad.axes[1]||0;
  // Use the dominant axis: the original keypad cannot move diagonally.
  if(Math.max(Math.abs(x),Math.abs(y))>.55){
    if(Math.abs(x)>Math.abs(y))keys.add(x<0?0x37:0x39);
    else keys.add(y<0?0x35:0x38);
  }
  return keys;
}
export function createGamepadRepeater(){
  const held=new Map<number,number>();
  return {
    reset(){held.clear();},
    update(keys:Set<number>,now:number){
      const events:number[]=[];
      for(const key of held.keys())if(!keys.has(key))held.delete(key);
      for(const key of keys){
        const next=held.get(key);
        if(next===undefined){events.push(key);held.set(key,now+350);}
        else if(directions.has(key)&&now>=next){events.push(key);held.set(key,now+110);}
      }
      return events;
    }
  };
}
