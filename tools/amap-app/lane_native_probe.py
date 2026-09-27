"""Offline pinned-native LNDS decoding experiment; NOT a production backend.

Requires unicorn. Executes the native parser 1ac94e8 and geometry builder
1225638 in bounded ARM64 emulation; only libc/allocator/math imports are
implemented here. No Android device, network, login or rendering involved.
Single threaded: mutex hooks do nothing; frees are deferred until emulator
teardown. This diagnostic uses at most a 64 MiB bump arena. It does not
establish coordinate-system or elevation semantics.
"""
from pathlib import Path
import struct,sys,json,math,argparse,hashlib,zlib
from unicorn import *
from unicorn.arm64_const import *
from pathlib import Path
import struct
class Elf:
 def __init__(self, path):
  self.d=Path(path).read_bytes();d=self.d;ph=struct.unpack_from('<Q',d,32)[0];pe,pn=struct.unpack_from('<HH',d,54);self.segs=[struct.unpack_from('<IIQQQQQQ',d,ph+i*pe) for i in range(pn)];so=struct.unpack_from('<Q',d,40)[0];se,sn=struct.unpack_from('<HH',d,58);self.sh=[struct.unpack_from('<IIQQQQIIQQ',d,so+i*se) for i in range(sn)]
 def read(self,a,n):
  for typ,flags,off,va,pa,fs,ms,al in self.segs:
   if typ==1 and va<=a and a+n<=va+fs:return self.d[off+a-va:off+a-va+n]
  raise ValueError(hex(a))
 def relocs(self):
  for h in self.sh:
   if h[1]==4:
    for off in range(h[4],h[4]+h[5],24):yield struct.unpack_from('<QQq',self.d,off)

def run(path, library, tile, block_id, output):
 if hashlib.sha256(Path(library).read_bytes()).hexdigest() != '91491e00f582f610fe36cdbc4ca03bef942d0da8ce24dc1f672c53be73e88e08':
  raise ValueError('requires pinned 17.00.0.2005 libamapr.so')
 if not 0 < tile < 2**64 or not 0 <= block_id <= 65535:raise ValueError('invalid identity')
 raw=Path(path).read_bytes()
 if not 8 < len(raw) <= 16*1024*1024:raise ValueError('invalid block size')
 if struct.unpack_from('<I',raw)[0] != zlib.crc32(raw[4:]):raise ValueError('block CRC mismatch')
 e=Elf(library);u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(0,0x3000000)
 for typ,flags,off,va,pa,fs,ms,al in e.segs:
  if typ==1:u.mem_write(va,e.d[off:off+fs])
 for a,info,c in e.relocs():
  if info&0xffffffff==1027:u.mem_write(a,struct.pack('<Q',c))
 u.mem_map(0x40000000,0x4000000);u.mem_map(0x50000000,0x200000);u.mem_map(0x51000000,0x1000000);u.mem_map(0x60000000,0x200000)
 u.reg_write(UC_ARM64_REG_TPIDR_EL0,0x60000000);u.reg_write(UC_ARM64_REG_CPACR_EL1,3<<20)
 names={'28435760': 'ldexp', '28435776': 'log', '28435792': 'exp', '28436000': 'atan', '28436416': 'cos', '28436432': 'sin', '28436448': 'tan', '28436912': 'pow', '28437632': 'atan2'}
 heap=[0x40000000];allocs=[]
 def hook(u,a,size,ud):
  x=[u.reg_read(r) for r in (UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2)]
  if a in (0x1b1e4a0,0x1b1e470,0x1b1e4c0,0x1b1e6f0,0x1b1eae0):
   assert x[2] <= 16*1024*1024, 'libc operation limit'
  if a in (0x1b1e510,0x1b1e4e0,0x1b1f6a0):
   n=x[0];assert n<0x2000000;n=(n+15)&~15;ret=heap[0];heap[0]+=n;assert heap[0]<0x44000000;allocs.append((ret,n));u.reg_write(UC_ARM64_REG_X0,ret)
  elif a==0x1b1e4a0:u.mem_write(x[0],bytes([x[1]&255])*x[2])
  elif a in (0x1b1e470,0x1b1e4c0):u.mem_write(x[0],bytes(u.mem_read(x[1],x[2])))
  elif a in (0x1b1e500,0x1b1e480,0x1b1e660,0x1b1e560,0x1b1e780,0x1b1e790):pass
  elif a==0x1b1e520:

   assert x[0] <= 1000000, 'hash table limit'
   n=max(2,x[0])
   while any(n%d==0 for d in range(2,math.isqrt(n)+1)):n+=1
   u.reg_write(UC_ARM64_REG_X0,n)
  elif a==0x1b1e6f0:
   aa=bytes(u.mem_read(x[0],x[2]));bb=bytes(u.mem_read(x[1],x[2]));u.reg_write(UC_ARM64_REG_X0,((aa>bb)-(aa<bb))&0xffffffffffffffff)
  elif names.get(str(a)) in ('pow','sqrt','sin','cos','atan','atan2','tan','log','exp','ldexp'):
   name=names[str(a)]
   d=[struct.unpack('<d',struct.pack('<Q',u.reg_read(reg)))[0] for reg in (UC_ARM64_REG_D0,UC_ARM64_REG_D1)]
   v=getattr(math,name)(*d) if name in ('pow','atan2') else math.ldexp(d[0],x[0]) if name=='ldexp' else getattr(math,name)(d[0])
   u.reg_write(UC_ARM64_REG_D0,struct.unpack('<Q',struct.pack('<d',v))[0])
  elif a==0x1b1e5d0:
   n=0
   while u.mem_read(x[0]+n,1)!=b'\0':
    n+=1
    assert n <= 1048576, 'string limit'
   u.reg_write(UC_ARM64_REG_X0,n)
  elif a==0x1b1e5e0:
   n=x[2];assert n <= 1048576, 'string limit';data=bytes(u.mem_read(x[1],n))+b'\0'
   if n<23:u.mem_write(x[0],(bytes([n*2])+data).ljust(24,b'\0'))
   else:
    cap=(n+16)&~15;ptr=heap[0];heap[0]+=cap;assert heap[0]<0x44000000;u.mem_write(ptr,data);u.mem_write(x[0],struct.pack('<QQQ',cap|1,n,ptr))
  elif a==0x1b1eae0:
   vals=struct.unpack('<'+'I'*x[2],u.mem_read(x[0],x[2]*4));idx=next((i for i,v in enumerate(vals) if v==x[1]&0xffffffff),None)
   u.reg_write(UC_ARM64_REG_X0,x[0]+idx*4 if idx is not None else 0)
  else:raise RuntimeError('unhandled import '+hex(a)+' '+names.get(str(a),'?'))
  u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook,begin=0x1b1e000,end=0x1b20000)
 u.mem_write(0x51000000,raw)
 u.mem_write(0x50000000,struct.pack('<QIiQQ',0x51000000,len(raw),-1,0,0))
 u.reg_write(UC_ARM64_REG_SP,0x601f0000);u.reg_write(UC_ARM64_REG_LR,0x60001000)
 u.reg_write(UC_ARM64_REG_X0,0x50000000);u.reg_write(UC_ARM64_REG_X1,0x50000100)
 try:u.emu_start(0x1ac94e8,0x60001000,count=100000000,timeout=30000000)
 except Exception as ex:print('error',ex,'pc',hex(u.reg_read(UC_ARM64_REG_PC)));raise
 out=struct.unpack('<Q',u.mem_read(0x50000100,8))[0]
 assert u.reg_read(UC_ARM64_REG_PC)==0x60001000, 'instruction/time limit'
 assert u.reg_read(UC_ARM64_REG_X0)==0 and out, 'native decoder failed'
 report={'input':str(path),'return':u.reg_read(UC_ARM64_REG_X0),'pc':hex(u.reg_read(UC_ARM64_REG_PC)),'object':hex(out),'allocations':allocs,'header':bytes(u.mem_read(out,0x210)).hex() if out else None}
 if out:
  def call(addr,*args):
   u.reg_write(UC_ARM64_REG_SP,0x601f0000);u.reg_write(UC_ARM64_REG_LR,0x60001000)
   for r,v in zip((UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3),args):u.reg_write(r,v)
   try:u.emu_start(addr,0x60001000,count=100000000,timeout=30000000)
   except Exception as ex:print('builder error',ex,'pc',hex(u.reg_read(UC_ARM64_REG_PC)));raise
   assert u.reg_read(UC_ARM64_REG_PC)==0x60001000
   return u.reg_read(UC_ARM64_REG_X0)
  ctx=0x500e0000
  call(0x1223f1c,ctx,0x80000)
  native_id=call(0x160d0e4,tile)
  u.mem_write(out,struct.pack('<H',block_id));u.mem_write(out+4,struct.pack('<I',native_id))
  assert call(0x1225638,ctx,out)==1, 'geometry conversion failed'
  call(0x1225cdc,ctx,0,native_id)
  base=struct.unpack('<Q',u.mem_read(ctx+0x80,8))[0];ptr=struct.unpack('<Q',u.mem_read(ctx+0x88,8))[0];capacity=struct.unpack('<I',u.mem_read(ctx+0x78,4))[0]
  length=base+capacity-ptr
  assert 0 < length <= 16*1024*1024
  fb=bytes(u.mem_read(ptr,length));Path(output).write_bytes(fb)
  report={'blockSha256':hashlib.sha256(raw).hexdigest(),'tileId':tile,'nativeTileId':native_id,'blockId':block_id,'flatbufferBytes':length,'flatbufferSha256':hashlib.sha256(fb).hexdigest()}
  Path(str(output)+'.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
 return u,out
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--lib',required=True);p.add_argument('--block',required=True)
 p.add_argument('--tile-id',required=True,type=int);p.add_argument('--block-id',required=True,type=int)
 p.add_argument('--output',required=True)
 a=p.parse_args();run(a.block,a.lib,a.tile_id,a.block_id,a.output)
