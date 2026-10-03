"""Local experiment: run the APK's tiny ARM64 XML serializer in Unicorn."""
import io
import struct
import sys
import zipfile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM
from unicorn.arm64_const import (UC_ARM64_REG_LR, UC_ARM64_REG_PC,
                                 UC_ARM64_REG_SP, UC_ARM64_REG_X0,
                                 UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                                 UC_ARM64_REG_X3)


with zipfile.ZipFile('.local-data/amap-app/amap-release.apk') as archive:
    raw = archive.read('lib/arm64-v8a/libiksemel.so')
elf = ELFFile(io.BytesIO(raw))
uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
uc.mem_map(0, 0x10000)
for seg in elf.iter_segments():
    if seg['p_type'] == 'PT_LOAD':
        uc.mem_write(seg['p_vaddr'], seg.data())
uc.mem_map(0x100000, 0x800000)
symbols = {symbol.name: symbol['st_value'] for symbol in elf.get_section_by_name('.dynsym').iter_symbols()}
hooks = {}
next_stub = 0x500000
for section in elf.iter_sections():
    if section['sh_type'] != 'SHT_RELA':
        continue
    table = elf.get_section(section['sh_link'])
    for rel in section.iter_relocations():
        if rel['r_info_type'] == 1027:
            uc.mem_write(rel['r_offset'], struct.pack('<Q', rel['r_addend']))
        elif rel['r_info_type'] == 1026:
            symbol = table.get_symbol(rel['r_info_sym'])
            if symbol['st_shndx'] != 'SHN_UNDEF' and symbol['st_value']:
                uc.mem_write(rel['r_offset'], struct.pack('<Q', symbol['st_value']))
            else:
                hooks[next_stub] = symbol.name
                uc.mem_write(rel['r_offset'], struct.pack('<Q', next_stub))
                next_stub += 4
        else:
            raise ValueError(rel['r_info_type'])

heap = 0x100000


def allocate(size):
    global heap
    result = heap
    heap += (max(1, size) + 15) & ~15
    if heap >= 0x4f0000:
        raise MemoryError('guest heap')
    return result


def put(value):
    data = value.encode() + b'\0'
    ptr = allocate(len(data))
    uc.mem_write(ptr, data)
    return ptr


def read(pointer, limit=1000000):
    data = bytearray()
    for index in range(limit):
        item = uc.mem_read(pointer + index, 1)[0]
        if item == 0:
            return bytes(data)
        data.append(item)
    raise ValueError('oversized guest string')


def on_code(engine, address, _size, _userdata):
    if address == 0x600000:
        engine.emu_stop()
        return
    name = hooks.get(address)
    if name is None:
        return
    a = engine.reg_read(UC_ARM64_REG_X0)
    b = engine.reg_read(UC_ARM64_REG_X1)
    c = engine.reg_read(UC_ARM64_REG_X2)
    result = 0
    if name == 'malloc':
        result = allocate(a)
    elif name == 'free':
        pass
    elif name == 'strlen':
        result = len(read(a))
    elif name == 'memcpy':
        engine.mem_write(a, bytes(engine.mem_read(b, c)))
        result = a
    elif name == 'memset':
        engine.mem_write(a, bytes([b & 255]) * c)
        result = a
    elif name == 'strcmp':
        aa, bb = read(a), read(b)
        result = 0 if aa == bb else (-1 if aa < bb else 1)
    elif name == 'strncmp':
        aa, bb = read(a)[:c], read(b)[:c]
        result = 0 if aa == bb else (-1 if aa < bb else 1)
    elif name == 'strdup':
        result = allocate(len(read(a)) + 1)
        engine.mem_write(result, read(a) + b'\0')
    elif name in ('strchr', '__strchr_chk'):
        value = read(a)
        offset = value.find(bytes([b & 255]))
        result = a + offset if offset >= 0 else 0
    elif name == 'strstr':
        offset = read(a).find(read(b))
        result = a + offset if offset >= 0 else 0
    elif name in ('__cxa_atexit', '__cxa_finalize'):
        pass
    elif name == '__stack_chk_fail':
        raise RuntimeError('guest stack check')
    else:
        raise RuntimeError('unsupported import ' + name)
    engine.reg_write(UC_ARM64_REG_X0, result)
    engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_LR))


uc.hook_add(UC_HOOK_CODE, on_code)


def call(name, *args):
    uc.reg_write(UC_ARM64_REG_SP, 0x8f0000)
    for register, value in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3), args):
        uc.reg_write(register, value)
    uc.reg_write(UC_ARM64_REG_LR, 0x600000)
    uc.emu_start(symbols[name], 0x600004, count=1000000)
    return uc.reg_read(UC_ARM64_REG_X0)


root = call('iks_new', put('etatrafficupdate'))
call('iks_insert_attrib', root, put('NaviID'), put('0123456789abcdef0123456789abcdef'))
info = call('iks_insert', root, put('ETAInfo'))
flag = call('iks_insert', info, put('ETAFlag'))
eta_flag = int(sys.argv[2]) if len(sys.argv) > 2 else 2
call('iks_insert_cdata', flag, put(str(eta_flag)), len(str(eta_flag)))
payload = sys.argv[1] if len(sys.argv) > 1 else '{"flag":7}'
if eta_flag:
    request = call('iks_insert', info, put('TRRequestData'))
    call('iks_insert_cdata', request, put(payload), len(payload.encode()))
buffer = call('iks_string', call('iks_stack', root), root)
print(repr(read(buffer)))
call('iks_delete', root)
