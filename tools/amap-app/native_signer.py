"""Optional isolated native getter experiment for the pinned 17.00 APK.

Requires locally supplied research assets; returns material only in memory.
Never call in the Flask worker itself. No Android runtime is started.
"""

def load_material(asset_dir):
    import struct,json
    from pathlib import Path
    from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC)
    p=asset_dir;d=(p/'libserverkey.so').read_bytes();u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    u.mem_map(0,0x40000);u.mem_write(0,d[:0x1000])
    phoff=struct.unpack_from('<Q',d,32)[0];pe,pn=struct.unpack_from('<HH',d,54)
    for i in range(pn):
     typ,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',d,phoff+i*pe)
     if typ==1:u.mem_write(va,d[off:off+fs])
    so=struct.unpack_from('<Q',d,40)[0];se,sn=struct.unpack_from('<HH',d,58);sh=[struct.unpack_from('<IIQQQQIIQQ',d,so+i*se) for i in range(sn)]
    sy=next(h for h in sh if h[1]==11);st=sh[sy[6]];ss=d[st[4]:st[4]+st[5]];syms=[]
    for off in range(sy[4],sy[4]+sy[5],24):
     nm,info,ot,sec,val,sz=struct.unpack_from('<IBBHQQ',d,off);syms.append(ss[nm:ss.index(b'\0',nm)].decode())
    u.mem_map(0x100000,0x1000000);heap=0x200000;hooks={};nextstub=0x110000
    for h in sh:
     if h[1]!=4:continue
     for off in range(h[4],h[4]+h[5],24):
      dst,info,add=struct.unpack_from('<QQq',d,off);typ=info&0xffffffff;si=info>>32
      if typ==1027:u.mem_write(dst,struct.pack('<Q',add))
      elif si:
       hooks[nextstub]=syms[si];u.mem_write(dst,struct.pack('<Q',nextstub));nextstub+=4
    vm,vt,env,et=0x120000,0x121000,0x122000,0x123000
    for obj,table in [(vm,vt),(env,et)]:
     u.mem_write(obj,struct.pack('<Q',table))
     for idx in range(240):
      hooks[nextstub]=('vm' if obj==vm else 'jni',idx);u.mem_write(table+8*idx,struct.pack('<Q',nextstub));nextstub+=4

    def cstr(addr):
     out=bytearray()
     for i in range(4096):
      c=u.mem_read(addr+i,1)[0]
      if not c:return out.decode('utf8',errors='replace')
      out.append(c)
     return '<long>'
    phase=False; captured=[]; cert_ptr=0x140000; cert=b''
    regs=[UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3];found=[]
    def hook(uc,addr,size,data):
     nonlocal heap
     if addr==0x130000:uc.emu_stop();return
     if addr not in hooks:return
     name=hooks[addr];x=[uc.reg_read(r) for r in regs];v=0
     if name=='signature-source':v=0x141000
     elif phase and name==('jni',173):v=0x142000
     elif phase and name==('jni',35):v=0x143000
     elif phase and name==('jni',184):v=cert_ptr
     elif phase and name==('jni',171):v=len(cert)
     elif phase and name==('jni',167):captured.append(cstr(x[1]));v=0x144000
     elif name in ['malloc','_Znam']:
      v=heap;heap+=(x[0]+15)&~15
     elif name in ['memcpy','strncpy']:
      uc.mem_write(x[0],bytes(uc.mem_read(x[1],x[2])));v=x[0]
     elif name=='memset':uc.mem_write(x[0],bytes([x[1]&255])*x[2]);v=x[0]
     elif name in ['strlen','__strlen_chk']:v=len(cstr(x[0]).encode())
     elif name==('vm',6):uc.mem_write(x[1],struct.pack('<Q',env))
     elif name==('jni',215):
      for i in range(x[3]):
       a,b,f=struct.unpack('<QQQ',uc.mem_read(x[2]+i*24,24));found.append(dict(name=cstr(a),signature=cstr(b),address=f))
     elif name in [('jni',6),('jni',33),('jni',113)]:
      v=0x125000
     elif isinstance(name,tuple):v=0x125000
     elif name in ['free','_ZdaPv','__cxa_atexit','__cxa_finalize','__android_log_print']:pass
     else:raise RuntimeError('unsupported import '+str(name))
     uc.reg_write(UC_ARM64_REG_X0,v);uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM64_REG_SP,0x1000000);u.reg_write(UC_ARM64_REG_X0,vm);u.reg_write(UC_ARM64_REG_LR,0x130000)
    u.emu_start(0x9d18,0x130004,count=1000000)

    from cryptography.hazmat.primitives.serialization import pkcs7,Encoding
    cert=pkcs7.load_der_pkcs7_certificates((p/'signing-certificate.rsa').read_bytes())[0].public_bytes(Encoding.DER)
    assert sum(x if x<128 else x-256 for x in cert)==0x3576
    u.mem_write(cert_ptr,cert);hooks[0x33b8]='signature-source';phase=True
    values={}
    for name in ['getAosChannel','getAosKey']:
     captured.clear();addr=next(x['address'] for x in found if x['name']==name)
     u.reg_write(UC_ARM64_REG_X0,env);u.reg_write(UC_ARM64_REG_LR,0x130000)
     u.emu_start(addr,0x130004,count=100000)
     if len(captured)!=1:raise ValueError('unexpected getter output')
     values[name]=captured[0]
    return values
