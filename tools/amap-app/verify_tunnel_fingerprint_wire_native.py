"""Probe pinned fingerprint container wire fields with the native decoder.

Synthetic minimal protobuf payload, empty nested collections. This does not
verify real downloaded payloads or decode the contained geometric records.
"""
import argparse,io,zipfile,struct,random,math
from inspect_vdr_model import inspect
from tunnel_fingerprint_container import decode
from tunnel_fingerprint_geometry import decode as decode_geometry, project
from tunnel_local_coordinates import DEGREES_TO_RADIANS, initialize_frame, initialize_packed_frame
from tunnel_polygon_matching import convex_hull
from elftools.elf.elffile import ELFFile
from unicorn import *
from unicorn.arm64_const import *
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('apk')
apk=parser.parse_args().apk;inspect(apk)
with zipfile.ZipFile(apk) as z: e=ELFFile(io.BytesIO(z.read('lib/arm64-v8a/libamaploc.so')))
u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
ss=[s for s in e.iter_segments() if s['p_type']=='PT_LOAD'];u.mem_map(0,(max(s['p_vaddr']+s['p_memsz'] for s in ss)+4095)&~4095)
for s in ss:u.mem_write(s['p_vaddr'],s.data())
for s in e.iter_sections():
 if s['sh_type']=='SHT_RELA':
  for r in s.iter_relocations():
   if r['r_info_type']==1027:u.mem_write(r['r_offset'],struct.pack('<Q',r['r_addend']))
u.mem_map(0x1000000,0x200000);heap=0x1100000;allocations={}
def varint(value):
 out=bytearray()
 while value>127:out.append((value&127)|128);value>>=7
 out.append(value);return bytes(out)
def blob(tag,value):return varint(tag*8+2)+varint(len(value))+value
# Nonempty repeated floor/tunnel/hull messages; payload geometry remains opaque.
record=bytes.fromhex('080b1016')+blob(3,b'name')+blob(4,b'geometry')+bytes.fromhex('2821')
nested=b''.join(blob(tag,record+(bytes.fromhex('302c') if tag==3 else b'')) for tag in (2,3,4) for _ in range(2))
payload=bytes.fromhex('08d936')+blob(2,b'a')+blob(3,b'b')+blob(4,nested)+blob(5,b'c')+blob(6,b'd')
u.mem_write(0x1008000,payload)
def hook(m,a,n,data):
 global heap
 if a==0x9f2bd0:
  x=m.reg_read(UC_ARM64_REG_X0);src=m.reg_read(UC_ARM64_REG_X1);size=m.reg_read(UC_ARM64_REG_X2)
  if size:m.mem_write(x,bytes(m.mem_read(src,size)))
 elif a==0x9f2ba0:
  x=m.reg_read(UC_ARM64_REG_X0);size=m.reg_read(UC_ARM64_REG_X2)
  if size:m.mem_write(x,bytes([m.reg_read(UC_ARM64_REG_X1)&255])*size)
 elif a in (0x9f2fb0,0x9f2b50):
  size=m.reg_read(UC_ARM64_REG_X0);m.reg_write(UC_ARM64_REG_X0,heap);heap+=(size+15)&~15
 elif a==0x9f3410:
  old=m.reg_read(UC_ARM64_REG_X0);size=m.reg_read(UC_ARM64_REG_X1)
  if old:
   assert old in allocations
   m.mem_write(heap,bytes(m.mem_read(old,min(size,allocations[old]))))
  allocations[heap]=size
  m.reg_write(UC_ARM64_REG_X0,heap);heap+=(size+15)&~15
 elif a in (0x9f2fc0,0x9f31b0,0x9f2e20):
  value=struct.unpack('<d',struct.pack('<Q',m.reg_read(UC_ARM64_REG_D0)))[0]
  if a==0x9f2e20:
   m.mem_write(m.reg_read(UC_ARM64_REG_X0),struct.pack('<d',math.sin(value)))
   m.mem_write(m.reg_read(UC_ARM64_REG_X1),struct.pack('<d',math.cos(value)))
  else:
   exponent=struct.unpack('<d',struct.pack('<Q',m.reg_read(UC_ARM64_REG_D1)))[0]
   result=math.sin(value) if a==0x9f2fc0 else math.pow(value,exponent)
   m.reg_write(UC_ARM64_REG_D0,struct.unpack('<Q',struct.pack('<d',result))[0])
 elif a in (0x9f2b20,0x9f2f80):pass
 else:raise RuntimeError('external '+hex(a)+' LR='+hex(m.reg_read(UC_ARM64_REG_LR)))
 m.reg_write(UC_ARM64_REG_PC,m.reg_read(UC_ARM64_REG_LR))
u.hook_add(UC_HOOK_CODE,hook,begin=0x9f2b00,end=0x9f5000)
for r,v in ((UC_ARM64_REG_X0,0x1000000),(UC_ARM64_REG_X1,0x1008000),(UC_ARM64_REG_X2,len(payload)),(UC_ARM64_REG_SP,0x10f0000),(UC_ARM64_REG_LR,0x10ff000),(UC_ARM64_REG_TPIDR_EL0,0x10fe000)):u.reg_write(r,v)
try:u.emu_start(0x695a88,0x10ff000,count=1000000)
except Exception as ex:print(ex,'PC',hex(u.reg_read(UC_ARM64_REG_PC)));raise
assert u.reg_read(UC_ARM64_REG_PC)==0x10ff000
assert u.reg_read(UC_ARM64_REG_X0)==1
assert struct.unpack('<I',u.mem_read(0x1000000,4))[0]==7001
for offset,expected in ((8,b'a\0'),(16,b'b\0'),(88,b'c\0'),(96,b'd\0')):
 pointer=struct.unpack('<Q',u.mem_read(0x1000000+offset,8))[0]
 assert bytes(u.mem_read(pointer,2))==expected
decoded=decode(payload)
assert decoded['version']==7001 and decoded['identifier']==b'b'
for offset,group in ((40,'floors'),(56,'tunnels'),(72,'hulls')):
 count=struct.unpack('<I',u.mem_read(0x1000000+offset,4))[0]
 pointer=struct.unpack('<Q',u.mem_read(0x1000000+offset+8,8))[0]
 assert count==2
 for index in range(count):
  values=struct.unpack('<iiQQii',u.mem_read(pointer+index*32,32))
  assert values[:2]==(11,22)
  assert bytes(u.mem_read(values[2],5))==b'name\0'
  assert struct.unpack('<I',u.mem_read(values[3],4))[0]==8
  assert bytes(u.mem_read(values[3]+4,8))==b'geometry'
  assert values[4]==33
  if offset==56:assert values[5]==44
  expected={1:values[0],2:values[1],3:b'name',4:b'geometry',5:values[4]}
  if offset==56:expected[6]=values[5]
  assert decoded[group][index]==expected
print('Native fingerprint container: six nonempty repeated records and scalar/string/bytes offsets verified')
# Compare the original packed-header reader, without calling projection or
# claiming that the resulting coordinates already match the map frame.
header=struct.pack('<4dHB2s4f',120.,30.,120.01,30.01,1,7,b'\x00\x00',10.,20.,30.,40.)
sample=struct.pack('<Hdd5h',9,120.005,30.005,-100,200,-300,400,-500)
geometry=struct.pack('<Id',1,123.)+header+sample
parsed=decode_geometry(geometry)[0]
u.mem_write(0x1009000,header+sample)
u.reg_write(UC_ARM64_REG_X24,0x1009000)
u.reg_write(UC_ARM64_REG_SP,0x10e0000)
u.reg_write(UC_ARM64_REG_X29,0x10e1000)
u.emu_start(0x69496c,0x694b50,count=1000)
assert u.reg_read(UC_ARM64_REG_PC)==0x694b50
assert u.reg_read(UC_ARM64_REG_X27)==len(parsed['samples'])
assert struct.unpack('<I',u.mem_read(0x10e003c,4))[0]==parsed['attribute']
assert struct.unpack('<2d',u.mem_read(0x10e0050,16))==parsed['endpoints'][:2]
assert struct.unpack('<2d',u.mem_read(0x10e0040,16))==parsed['endpoints'][2:]
assert struct.unpack('<2d',u.mem_read(0x10e0080,16))==parsed['baselines'][1:3]
def native_double(register):return struct.unpack('<d',struct.pack('<Q',u.reg_read(register)))[0]
assert native_double(UC_ARM64_REG_D12)==parsed['baselines'][0]
assert native_double(UC_ARM64_REG_D13)==parsed['baselines'][3]
print('Native tunnel packed header: endpoints, sample count, attribute and baselines match Python')
u.reg_write(UC_ARM64_REG_X8,0x1009000)
u.mem_write(0x10e0070,struct.pack('<2d',50.,50.))
u.emu_start(0x694b5c,0x694c9c,count=1000)
assert u.reg_read(UC_ARM64_REG_PC)==0x694c9c
reading=parsed['samples'][0]
assert u.reg_read(UC_ARM64_REG_X26)==reading['id']
assert native_double(UC_ARM64_REG_D15)==reading['coordinates'][0]
assert native_double(UC_ARM64_REG_D8)==reading['coordinates'][1]
assert struct.unpack('<3f',u.mem_read(0x10e1000-0xd0,12))==tuple(
 parsed['baselines'][axis+1]+reading['packed_values'][axis+2]/50 for axis in range(3))
assert struct.unpack('<3f',u.mem_read(0x10e1000-0xd0,12))==reading['vector']
scalar=struct.unpack('<f',struct.pack('<I',u.reg_read(UC_ARM64_REG_S14)))[0]
assert scalar==parsed['baselines'][0]+reading['packed_values'][0]/100
assert scalar==reading['scalar']
assert u.reg_read(UC_ARM64_REG_X28)==reading['packed_values'][1]
print('Native tunnel sample: signed values and /50, /100 scaling verified')
frame=(2.09,.52,5500000.,6370000.)
u.reg_write(UC_ARM64_REG_X19,0x100d000)
u.mem_write(0x100d008,struct.pack('<2d',*frame[:2]))
u.mem_write(0x100d020,struct.pack('<2d',*frame[2:]))
for register,value in ((UC_ARM64_REG_D3,frame[2]),(UC_ARM64_REG_D4,frame[3])):
 u.reg_write(register,struct.unpack('<Q',struct.pack('<d',value))[0])
u.reg_write(UC_ARM64_REG_D11,struct.unpack('<Q',struct.pack('<d',DEGREES_TO_RADIANS))[0])
u.emu_start(0x694cec,0x694d04,count=1000)
native_point=struct.unpack('<2d',u.mem_read(0x10e1000-0xb8,16))
projected=project([parsed],*frame)[0]
assert max(abs(a-b) for a,b in zip(native_point,projected['samples'][0]['local']))<1e-7
assert projected['polygon']==[projected['samples'][0]['local']]
print('Native tunnel local projection agrees with existing TMC coordinate primitive')
rng=random.Random(20260929)
fixtures=[[],[(1.,2.)],[(1.,2.),(3.,4.),(2.,0.)],[(1.,1.)]*4,
          [(0.,0.),(1.,1.),(2.,2.),(3.,3.)]]
fixtures += [[(rng.uniform(-20,20),rng.uniform(-20,20)) for _ in range(rng.randint(4,40))] for _ in range(50)]
for points in fixtures:
 start=0x100b000;end=start+len(points)*16
 if points:u.mem_write(start,b''.join(struct.pack('<2d',*p) for p in points))
 u.mem_write(0x100a000,struct.pack('<3Q',start,end,end))
 u.mem_write(0x100c000,bytes(24))
 for register,value in ((UC_ARM64_REG_X0,0x100a000),(UC_ARM64_REG_X8,0x100c000),
                        (UC_ARM64_REG_SP,0x10f0000),(UC_ARM64_REG_LR,0x10ff000)):
  u.reg_write(register,value)
 u.emu_start(0x691690,0x10ff000,count=1000000)
 assert u.reg_read(UC_ARM64_REG_PC)==0x10ff000
 begin,end,_=struct.unpack('<3Q',u.mem_read(0x100c000,24))
 actual=[struct.unpack('<2d',u.mem_read(address,16)) for address in range(begin,end,16)]
 assert actual==convex_hull(points),(points,actual,convex_hull(points))
print('Native tunnel convex hull: 55 degenerate and randomized cases match Python')



# Execute the complete frame initializer with only imported libm calls hooked.
frame_rng=random.Random(20260929)
origins=[(0.,0.,0.),(30.,120.,5.),(-45.,-100.,1500.),(89.9,179.,-20.)]
origins += [(frame_rng.uniform(-89,89),frame_rng.uniform(-180,180),frame_rng.uniform(-100,5000)) for _ in range(100)]
for origin in origins:
 u.mem_write(0x100a000,struct.pack('<3d',*origin))
 u.mem_write(0x100b000,bytes(64))
 for register,value in ((UC_ARM64_REG_X1,0x100a000),(UC_ARM64_REG_X2,0x100b000),(UC_ARM64_REG_SP,0x10f0000),(UC_ARM64_REG_LR,0x10ff000)):
  u.reg_write(register,value)
 u.emu_start(0x6ada54,0x10ff000,count=10000)
 assert u.reg_read(UC_ARM64_REG_PC)==0x10ff000
 actual=struct.unpack('<5d',u.mem_read(0x100b008,40))
 expected=initialize_frame(*origin)
 assert actual[2]==origin[2]
 for got,wanted in zip((actual[0],actual[1],actual[3],actual[4]),expected):
  assert math.isclose(got,wanted,rel_tol=2e-15,abs_tol=1e-8),(origin,got,wanted)
print('Native fingerprint frame initializer: 104 origin/altitude cases match Python')

# Include the packed-coordinate adapter, TLS guard, initialized flag and return.
for origin in origins:
 packed=struct.pack('<iif',round(origin[1]*10000000),round(origin[0]*10000000),origin[2])
 u.mem_write(0x100a000,packed)
 u.mem_write(0x100b000,bytes(0x200))
 for register,value in ((UC_ARM64_REG_X0,0x100b000),(UC_ARM64_REG_X1,0x100a000),(UC_ARM64_REG_SP,0x10f0000),(UC_ARM64_REG_LR,0x10ff000),(UC_ARM64_REG_TPIDR_EL0,0x10fe000)):
  u.reg_write(register,value)
 u.emu_start(0x6aa8f4,0x10ff000,count=10000)
 assert u.reg_read(UC_ARM64_REG_PC)==0x10ff000
 assert bytes(u.mem_read(0x100b100,1))==b'\x01'
 actual=struct.unpack('<5d',u.mem_read(0x100b108,40))
 for got,wanted in zip((actual[0],actual[1],actual[3],actual[4]),initialize_packed_frame(packed)):
  assert math.isclose(got,wanted,rel_tol=2e-15,abs_tol=1e-8),(packed,got,wanted)
print('Native packed frame adapter: 104 coordinate swaps/scales and initialized flags verified')
