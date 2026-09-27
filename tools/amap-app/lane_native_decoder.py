"""Pinned LNDS decoder. Run only inside the bounded map helper subprocess.

64 MiB heap, 16 MiB input/output and per-call native instruction/time limits.
Only libc/allocator/math imports are simulated; unknown imports fail closed.
Single-thread locks are no-ops and frees are deferred to emulator teardown.
"""
from pathlib import Path
import struct, math, hashlib, zlib
from unicorn import *
from unicorn.arm64_const import *
from pathlib import Path
import struct

class Elf:

    def __init__(self, data):
        self.d = data
        d = self.d
        ph = struct.unpack_from('<Q', d, 32)[0]
        pe, pn = struct.unpack_from('<HH', d, 54)
        self.segs = [struct.unpack_from('<IIQQQQQQ', d, ph + i * pe) for i in range(pn)]
        so = struct.unpack_from('<Q', d, 40)[0]
        se, sn = struct.unpack_from('<HH', d, 58)
        self.sh = [struct.unpack_from('<IIQQQQIIQQ', d, so + i * se) for i in range(sn)]

    def read(self, a, n):
        for typ, flags, off, va, pa, fs, ms, al in self.segs:
            if typ == 1 and va <= a and (a + n <= va + fs):
                return self.d[off + a - va:off + a - va + n]
        raise ValueError(hex(a))

    def relocs(self):
        for h in self.sh:
            if h[1] == 4:
                for off in range(h[4], h[4] + h[5], 24):
                    yield struct.unpack_from('<QQq', self.d, off)

def decode(raw, library, tile, block_id):
    if hashlib.sha256(library).hexdigest() != '91491e00f582f610fe36cdbc4ca03bef942d0da8ce24dc1f672c53be73e88e08':
        raise ValueError('requires pinned 17.00.0.2005 libamapr.so')
    if not 0 < tile < 2 ** 64 or not 0 <= block_id <= 65535:
        raise ValueError('invalid identity')
    if not 8 < len(raw) <= 16 * 1024 * 1024:
        raise ValueError('invalid block size')
    if struct.unpack_from('<I', raw)[0] != zlib.crc32(raw[4:]):
        raise ValueError('block CRC mismatch')
    e = Elf(library)
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    u.mem_map(0, 50331648)
    for typ, flags, off, va, pa, fs, ms, al in e.segs:
        if typ == 1:
            u.mem_write(va, e.d[off:off + fs])
    for a, info, c in e.relocs():
        if info & 4294967295 == 1027:
            u.mem_write(a, struct.pack('<Q', c))
    u.mem_map(1073741824, 67108864)
    u.mem_map(1342177280, 2097152)
    u.mem_map(1358954496, 16777216)
    u.mem_map(1610612736, 2097152)
    u.reg_write(UC_ARM64_REG_TPIDR_EL0, 1610612736)
    u.reg_write(UC_ARM64_REG_CPACR_EL1, 3 << 20)
    names = {'28435760': 'ldexp', '28435776': 'log', '28435792': 'exp', '28436000': 'atan', '28436416': 'cos', '28436432': 'sin', '28436448': 'tan', '28436912': 'pow', '28437632': 'atan2'}
    heap = [1073741824]
    allocs = []

    def hook(u, a, size, ud):
        x = [u.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
        if a in (28435616, 28435568, 28435648, 28436208, 28437216):
            if not x[2] <= 16 * 1024 * 1024:
                raise ValueError('libc operation limit')
        if a in (28435728, 28435680, 28440224):
            n = x[0]
            if not n < 33554432:
                raise ValueError('native decoder limit')
            n = n + 15 & ~15
            ret = heap[0]
            heap[0] += n
            if not heap[0] < 1140850688:
                raise ValueError('native decoder limit')
            allocs.append((ret, n))
            u.reg_write(UC_ARM64_REG_X0, ret)
        elif a == 28435616:
            u.mem_write(x[0], bytes([x[1] & 255]) * x[2])
        elif a in (28435568, 28435648):
            u.mem_write(x[0], bytes(u.mem_read(x[1], x[2])))
        elif a in (28435712, 28435584, 28436064, 28435808, 28436352, 28436368):
            pass
        elif a == 28435744:
            if not x[0] <= 1000000:
                raise ValueError('hash table limit')
            n = max(2, x[0])
            while any((n % d == 0 for d in range(2, math.isqrt(n) + 1))):
                n += 1
            u.reg_write(UC_ARM64_REG_X0, n)
        elif a == 28436208:
            aa = bytes(u.mem_read(x[0], x[2]))
            bb = bytes(u.mem_read(x[1], x[2]))
            u.reg_write(UC_ARM64_REG_X0, (aa > bb) - (aa < bb) & 18446744073709551615)
        elif names.get(str(a)) in ('pow', 'sqrt', 'sin', 'cos', 'atan', 'atan2', 'tan', 'log', 'exp', 'ldexp'):
            name = names[str(a)]
            d = [struct.unpack('<d', struct.pack('<Q', u.reg_read(reg)))[0] for reg in (UC_ARM64_REG_D0, UC_ARM64_REG_D1)]
            v = getattr(math, name)(*d) if name in ('pow', 'atan2') else math.ldexp(d[0], x[0]) if name == 'ldexp' else getattr(math, name)(d[0])
            u.reg_write(UC_ARM64_REG_D0, struct.unpack('<Q', struct.pack('<d', v))[0])
        elif a == 28435920:
            n = 0
            while u.mem_read(x[0] + n, 1) != b'\x00':
                n += 1
                if not n <= 1048576:
                    raise ValueError('string limit')
            u.reg_write(UC_ARM64_REG_X0, n)
        elif a == 28435936:
            n = x[2]
            if not n <= 1048576:
                raise ValueError('string limit')
            data = bytes(u.mem_read(x[1], n)) + b'\x00'
            if n < 23:
                u.mem_write(x[0], (bytes([n * 2]) + data).ljust(24, b'\x00'))
            else:
                cap = n + 16 & ~15
                ptr = heap[0]
                heap[0] += cap
                if not heap[0] < 1140850688:
                    raise ValueError('native decoder limit')
                u.mem_write(ptr, data)
                u.mem_write(x[0], struct.pack('<QQQ', cap | 1, n, ptr))
        elif a == 28437216:
            vals = struct.unpack('<' + 'I' * x[2], u.mem_read(x[0], x[2] * 4))
            idx = next((i for i, v in enumerate(vals) if v == x[1] & 4294967295), None)
            u.reg_write(UC_ARM64_REG_X0, x[0] + idx * 4 if idx is not None else 0)
        else:
            raise RuntimeError('unhandled import ' + hex(a) + ' ' + names.get(str(a), '?'))
        u.reg_write(UC_ARM64_REG_PC, u.reg_read(UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook, begin=28434432, end=28442624)
    u.mem_write(1358954496, raw)
    u.mem_write(1342177280, struct.pack('<QIiQQ', 1358954496, len(raw), -1, 0, 0))
    u.reg_write(UC_ARM64_REG_SP, 1612644352)
    u.reg_write(UC_ARM64_REG_LR, 1610616832)
    u.reg_write(UC_ARM64_REG_X0, 1342177280)
    u.reg_write(UC_ARM64_REG_X1, 1342177536)
    try:
        u.emu_start(28087528, 1610616832, count=100000000, timeout=30000000)
    except Exception:
        raise
    out = struct.unpack('<Q', u.mem_read(1342177536, 8))[0]
    if not u.reg_read(UC_ARM64_REG_PC) == 1610616832:
        raise ValueError('instruction/time limit')
    if not (u.reg_read(UC_ARM64_REG_X0) == 0 and out):
        raise ValueError('native decoder failed')
    if out:

        def call(addr, *args):
            u.reg_write(UC_ARM64_REG_SP, 1612644352)
            u.reg_write(UC_ARM64_REG_LR, 1610616832)
            for r, v in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3), args):
                u.reg_write(r, v)
            try:
                u.emu_start(addr, 1610616832, count=100000000, timeout=30000000)
            except Exception:
                raise
            if not u.reg_read(UC_ARM64_REG_PC) == 1610616832:
                raise ValueError('native decoder limit')
            return u.reg_read(UC_ARM64_REG_X0)
        ctx = 1343094784
        call(19021596, ctx, 524288)
        native_id = call(23122148, tile)
        u.mem_write(out, struct.pack('<H', block_id))
        u.mem_write(out + 4, struct.pack('<I', native_id))
        if not call(19027512, ctx, out) == 1:
            raise ValueError('geometry conversion failed')
        call(19029212, ctx, 0, native_id)
        base = struct.unpack('<Q', u.mem_read(ctx + 128, 8))[0]
        ptr = struct.unpack('<Q', u.mem_read(ctx + 136, 8))[0]
        capacity = struct.unpack('<I', u.mem_read(ctx + 120, 4))[0]
        length = base + capacity - ptr
        if not 0 < length <= 16 * 1024 * 1024:
            raise ValueError('native decoder limit')
        fb = bytes(u.mem_read(ptr, length))
    return fb
