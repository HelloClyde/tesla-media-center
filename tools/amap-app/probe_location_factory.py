"""Bounded offline probe of the pinned APK's location factory.

Research dependencies: unicorn, pyelftools. No network or navigation outputs are fabricated.
Only explicitly modeled cooperative runtime primitives are supplied. Stops on the first unsupported import.
The zero-filled service table tests dependency reachability, not valid init.
"""
import argparse
import hashlib
import io
import json
import struct
import zipfile
import time
from pathlib import Path
from native_thread_scheduler import NativeThreads
from native_probe_filesystem import ProbeFilesystem
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_TPIDR_EL0, UC_ARM64_REG_X29, UC_ARM64_REG_X8, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6

EXPECTED_LIBRARIES = {
    'libamapr.so': '91491e00f582f610fe36cdbc4ca03bef942d0da8ce24dc1f672c53be73e88e08',
    'libamapnsq.so': 'd87051d18867601db169767f0d39bdd2ed7c8c6a376553bbbbc185e9f20753cc',
    'libamapmain.so': '969656e13df0dc6bec0fdf6b685b7788ba1b50ffadce98d5357780d76450c2c9',
    'liblocation_kit.so': 'f1967ca7a1fd5fc82001add38dd388c6894ad7530d79a00dd199f19080e604ba',
    'libamaploc.so': '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34',
    'libloc_base.so': '8e5cc122e0d78002188690480e0bde2e45aa108deff7b124622035b5f2282178',
    'libc++_shared.so': 'd523468d62d9b603cb3354294d70d4b2feabf2c3f1e43b0c96c9aabf32813708',
    'libc.so': 'dba9e91341c1ac3213f939e8ea796c2ef08e8ceb8c46a2c33919902b7bdf66f6',
}


def probe(apk, bionic=None, data_module=False):
    with zipfile.ZipFile(apk) as archive:
        raw = archive.read('lib/arm64-v8a/liblocation_kit.so')
    if hashlib.sha256(raw).hexdigest() != EXPECTED_LIBRARIES['liblocation_kit.so']:
        raise ValueError('Unsupported location-kit binary; inspect the new sample first')
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    libraries = {}
    exports = {}
    with zipfile.ZipFile(apk) as archive:
        for index, name in enumerate(('liblocation_kit.so', 'libamaploc.so', 'libloc_base.so', 'libc++_shared.so') + (('libc.so',) if bionic else ()) + ('libamapmain.so',) + (('libamapr.so', 'libamapnsq.so') if data_module else ())):
            data = Path(bionic).read_bytes() if name == 'libc.so' else archive.read('lib/arm64-v8a/' + name)
            if hashlib.sha256(data).hexdigest() != EXPECTED_LIBRARIES[name]:
                raise ValueError(f'Unsupported binary: {name}')
            elf = ELFFile(io.BytesIO(data))
            base = 0x10000000 + index * 0x4000000
            segments = [segment for segment in elf.iter_segments() if segment['p_type'] == 'PT_LOAD']
            limit = max(segment['p_vaddr'] + segment['p_memsz'] for segment in segments)
            if limit > 0x4000000:
                raise ValueError('Library mapping limit exceeded')
            uc.mem_map(base, (limit + 4095) & ~4095)
            for segment in segments:
                uc.mem_write(base + segment['p_vaddr'], segment.data())
            libraries[name] = (elf, base)
            for symbol in elf.get_section_by_name('.dynsym').iter_symbols():
                if symbol['st_shndx'] != 'SHN_UNDEF' and symbol.name:
                    exports.setdefault(symbol.name, base + symbol['st_value'])
    uc.mem_map(0x1000000, 0x200000)
    entry = exports['CreateLocationKitInternal']
    hooks = {}; stub = 0x1000000; linked = []
    for library, (elf, base) in libraries.items():
        for section in elf.iter_sections():
            if section['sh_type'] != 'SHT_RELA':
                continue
            table = elf.get_section(section['sh_link'])
            for relocation in section.iter_relocations():
                kind = relocation['r_info_type']; addend = relocation['r_addend']
                if kind == 1027:
                    value = base + addend
                elif kind in (257, 1025, 1026) and relocation['r_info_sym']:
                    symbol = table.get_symbol(relocation['r_info_sym'])
                    if symbol['st_shndx'] != 'SHN_UNDEF':
                        value = base + symbol['st_value'] + addend
                    elif symbol.name in exports:
                        value = exports[symbol.name] + addend
                        linked.append(symbol.name)
                    else:
                        value = stub; hooks[stub] = symbol.name; stub += 4
                elif kind == 0:
                    continue
                else:
                    raise ValueError(f'Unsupported relocation {kind}')
                uc.mem_write(base + relocation['r_offset'], struct.pack('<Q', value))
    if bionic:
        elf, base = libraries['libc.so']
        for name in ('malloc', 'calloc', 'realloc', 'free', 'memset', 'memcpy', 'memmove', 'strlen', 'posix_memalign',
                     'getauxval', '__system_property_get', 'syscall', '__cxa_atexit', 'gettimeofday', 'clock_gettime',
                     'pthread_key_create', 'pthread_getspecific', 'pthread_setspecific', 'pthread_once',
                     'pthread_mutexattr_init', 'pthread_mutexattr_settype', 'pthread_mutexattr_destroy',
                     'pthread_mutex_init', 'pthread_mutex_lock', 'pthread_mutex_unlock', 'pthread_mutex_destroy',
                     'pthread_condattr_init', 'pthread_condattr_setclock', 'pthread_condattr_destroy',
                     'pthread_cond_init', 'pthread_cond_destroy',
                     'pthread_rwlock_init', 'pthread_create', 'pthread_self', 'pthread_detach', 'pthread_setname_np'):
            for symbol in elf.get_section_by_name('.dynsym').get_symbol_by_name(name) or []:
                hooks[base + symbol['st_value']] = name
    uc.mem_map(0x3000000, 0x2000000)
    heap = 0x3000000; sentinel = 0x10f0000
    allocations = {}
    report = {'engine_ready': False, 'position_output_verified': False,
              'entry': hex(entry), 'linked_engine_imports': sorted(set(linked)),
              'initializers_executed': False, 'calls': [], 'stop_reason': 'instruction_or_time_limit'}

    phdr_entries = []
    for index, (name, (elf, base)) in enumerate(libraries.items()):
        info = 0x11a0000 + index * 64; label = 0x11b0000 + index * 256
        uc.mem_write(label, ('/lib/arm64-v8a/' + name).encode() + bytes([0]))
        uc.mem_write(info, struct.pack('<QQQH6xQQQQ', base, label, base + elf['e_phoff'], elf['e_phnum'], len(libraries), 0, 0, 0))
        phdr_entries.append(info)
    dl_error = False
    dl_pending = []; dl_return = 0x10d0000
    exit_handlers = []
    tls_keys = {}; tls_values = {}
    once_done = set(); once_pending = []; once_return = 0x10e0000
    mutexes = {}; attributes = {}; conditions = set(); condition_attributes = {}

    threads = NativeThreads(uc, report)

    def hook(machine, address, size, _):
        nonlocal heap, dl_error
        if threads.on_code(address): return
        if address == dl_return:
            state = dl_pending[-1]; result = machine.reg_read(UC_ARM64_REG_X0)
            state['index'] += 1
            if result == 0 and state['index'] < len(phdr_entries):
                machine.reg_write(UC_ARM64_REG_X0, phdr_entries[state['index']])
                machine.reg_write(UC_ARM64_REG_X1, 64)
                machine.reg_write(UC_ARM64_REG_X2, state['data'])
                machine.reg_write(UC_ARM64_REG_LR, dl_return)
                machine.reg_write(UC_ARM64_REG_PC, state['callback'])
            else:
                dl_pending.pop()
                machine.reg_write(UC_ARM64_REG_PC, state['return'])
            return
        if address == exports.get('__cxa_throw'):
            report['stop_reason'] = 'native_exception'
            info = machine.reg_read(UC_ARM64_REG_X1)
            try:
                pointer = struct.unpack('<Q', machine.mem_read(info + 8, 8))[0]
                value = bytearray()
                for index in range(256):
                    char = machine.mem_read(pointer + index, 1)[0]
                    if not char: break
                    value.append(char)
                report['exception_type'] = value.decode('utf8', errors='replace')
            except UcError:
                report['exception_type'] = 'unreadable'
            report['exception_caller'] = hex(machine.reg_read(UC_ARM64_REG_LR))
            frame = machine.reg_read(UC_ARM64_REG_X29); frames = []
            for _ in range(12):
                if not 0x11d0000 <= frame < 0x11f0000: break
                frame, lr = struct.unpack('<QQ', machine.mem_read(frame, 16))
                frames.append(hex(lr))
            report['exception_frames'] = frames
            machine.emu_stop()
            return
        if address == once_return:
            control, target = once_pending.pop()
            once_done.add(control)
            machine.mem_write(control, struct.pack('<I', 2))
            machine.reg_write(UC_ARM64_REG_X0, 0)
            machine.reg_write(UC_ARM64_REG_PC, target)
            return
        if address == sentinel:
            report['stop_reason'] = 'returned_unverified'; report['return_value'] = hex(machine.reg_read(UC_ARM64_REG_X0)); machine.emu_stop(); return
        name = hooks.get(address)
        if name is None:
            return
        report['calls'].append(name)
        a, b, c = [machine.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
        report['last_import_arguments'] = [hex(a), hex(b), hex(c)]
        if name in ('_Znwm', '_ZnwmRKSt9nothrow_t', 'malloc'):
            if a > 0x1000000 or heap + a >= 0x5000000:
                raise ValueError('Allocation bound exceeded')
            result = (heap + 15) & ~15; heap = result + ((max(a, 1) + 15) & ~15)
            allocations[result] = a
        elif name in ('calloc', 'realloc'):
            size = a * b if name == 'calloc' else b
            if name == 'realloc' and a and a not in allocations:
                raise ValueError(f'Realloc of untracked allocation {hex(a)}')
            if size > 0x1000000 or heap + size + 16 >= 0x5000000:
                raise ValueError('Allocation bound exceeded')
            result = (heap + 15) & ~15
            heap = result + ((max(size, 1) + 15) & ~15)
            if name == 'calloc':
                machine.mem_write(result, bytes(size))
            elif a:
                machine.mem_write(result, bytes(machine.mem_read(a, min(allocations[a], size))))
                del allocations[a]
            allocations[result] = size
        elif name == 'posix_memalign':
            if b < 8 or b & (b - 1):
                result = 22
            else:
                pointer = (heap + b - 1) & ~(b - 1)
                if c > 0x1000000 or pointer + c >= 0x5000000:
                    raise ValueError('Aligned allocation bound exceeded')
                heap = pointer + c
                allocations[pointer] = c
                machine.mem_write(a, struct.pack('<Q', pointer)); result = 0
        elif name == 'memset':
            if c > 0x1000000:
                raise ValueError('memset bound exceeded')
            machine.mem_write(a, bytes([b & 255]) * c); result = a
        elif name in ('memcpy', 'memmove'):
            if c > 0x1000000:
                raise ValueError('Copy bound exceeded')
            machine.mem_write(a, bytes(machine.mem_read(b, c))); result = a
        elif name == 'strlen':
            result = 0
            while result < 65536 and machine.mem_read(a + result, 1)[0]:
                result += 1
            if result == 65536:
                raise ValueError('String bound exceeded')
        elif name == 'free':
            # Monotonic research allocator: memory remains mapped until probe exit.
            allocations.pop(a, None)
            result = 0
        elif name == '__android_log_print':
            # No Android log daemon in the harness; discard diagnostics only.
            result = 0
        elif name == 'dlopen':
            library = bytes(machine.mem_read(a, 256)).split(bytes([0]))[0].decode('utf8', errors='replace')
            item = libraries.get(library.rsplit('/', 1)[-1])
            result = item[1] if item else 0
            if not item: report.setdefault('missing_libraries', []).append(library)
            dl_error = not bool(item)
        elif name == 'dlsym':
            symbol_name = bytes(machine.mem_read(b, 512)).split(bytes([0]))[0].decode('utf8', errors='replace')
            if a in (0, 0xffffffffffffffff):
                result = exports.get(symbol_name, 0)
            else:
                item = next(((elf, base) for elf, base in libraries.values() if base == a), None)
                matches = item[0].get_section_by_name('.dynsym').get_symbol_by_name(symbol_name) if item else []
                result = next((item[1] + symbol['st_value'] for symbol in (matches or []) if symbol['st_shndx'] != 'SHN_UNDEF'), 0)
            dl_error = not bool(result)
        elif name == 'dlerror':
            machine.mem_write(0x11c0000, b'Library or symbol unavailable in offline harness'+bytes([0]))
            result = 0x11c0000 if dl_error else 0; dl_error = False
        elif name == 'dlclose':
            result = 0 if any(base == a for _, base in libraries.values()) else (1 << 64) - 1
        elif name == 'dl_iterate_phdr':
            dl_pending.append({'callback': a, 'data': b, 'index': 0, 'return': machine.reg_read(UC_ARM64_REG_LR)})
            machine.reg_write(UC_ARM64_REG_X0, phdr_entries[0])
            machine.reg_write(UC_ARM64_REG_X1, 64)
            machine.reg_write(UC_ARM64_REG_X2, b)
            machine.reg_write(UC_ARM64_REG_LR, dl_return)
            machine.reg_write(UC_ARM64_REG_PC, a)
            return
        elif name == 'gettimeofday':
            now = time.time_ns()
            if a: machine.mem_write(a, struct.pack('<qq', now // 1000000000, (now % 1000000000) // 1000))
            if b: machine.mem_write(b, bytes(8))
            result = 0
        elif name == 'clock_gettime':
            if a not in (0, 1, 6, 7):
                raise ValueError(f'Unsupported clock {a}')
            # Linux/Android clocks 6 and 7 are MONOTONIC_COARSE and BOOTTIME.
            # Use the host clocks with the same IDs.
            now = time.clock_gettime_ns(a) if a in (6, 7) else (time.time_ns() if a == 0 else time.monotonic_ns())
            machine.mem_write(b, struct.pack('<qq', now // 1000000000, now % 1000000000)); result = 0
        elif name == 'syscall' and a == 98:
            operation = c & 127
            value = machine.reg_read(UC_ARM64_REG_X3)
            timeout_pointer = machine.reg_read(UC_ARM64_REG_X4)
            bitset = machine.reg_read(UC_ARM64_REG_X6) if operation in (9, 10) else 0xffffffff
            if operation in (0, 9):
                observed = struct.unpack('<I', machine.mem_read(b, 4))[0]
                if observed != (value & 0xffffffff):
                    machine.mem_write(machine.reg_read(UC_ARM64_REG_TPIDR_EL0) + 16, struct.pack('<I', 11))
                    result = 0xffffffffffffffff
                else:
                    deadline = None
                    if timeout_pointer:
                        seconds, nanos = struct.unpack('<qq', machine.mem_read(timeout_pointer, 16))
                        deadline = seconds + nanos / 1000000000
                        if operation == 0: deadline += time.monotonic()
                    machine.reg_write(UC_ARM64_REG_X0, 0)
                    machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))
                    threads.block('futex', b, deadline, bool(c & 256), bitset)
                    return
            elif operation in (1, 10):
                result = threads.wake('futex', b, value, bitset)
            else:
                report['stop_reason'] = 'unsupported_futex'; report['futex_operation'] = operation
                machine.emu_stop(); return
        elif name == 'syscall' and a == 178:
            result = threads.current + 1  # Distinct emulated kernel thread IDs.
        elif name == '__system_property_get':
            # This offline harness has no Android system properties.
            machine.mem_write(b, bytes([0])); result = 0
        elif name == 'getauxval':
            values = {6: 4096, 16: 3, 26: 0}  # Page size, baseline ARM64 FP/ASIMD, HWCAP2.
            if a not in values:
                report['stop_reason'] = 'unsupported_auxval'; report['auxval'] = a
                machine.emu_stop(); return
            result = values[a]
        elif name in ('__cxa_atexit', '__aeabi_atexit'):
            exit_handlers.append((a, b, c)); result = 0
        elif name == 'pthread_create':
            argument = machine.reg_read(UC_ARM64_REG_X3)
            thread = threads.spawn(c, argument)
            machine.mem_write(a, struct.pack('<Q', thread))
            result = 0
        elif name == 'pthread_self':
            result = threads.current
        elif name == 'pthread_detach':
            result = 0 if a in threads.tasks else 3
        elif name == 'pthread_setname_np':
            result = 0 if a in threads.tasks else 3
        elif name == 'pthread_key_create':
            key = len(tls_keys) + 1; tls_keys[key] = b
            machine.mem_write(a, struct.pack('<I', key)); result = 0
        elif name == 'pthread_getspecific':
            result = tls_values.get((threads.current, a), 0)
        elif name == 'pthread_setspecific':
            if a not in tls_keys:
                report['unknown_tls_key'] = a
                report['tls_caller'] = hex(machine.reg_read(UC_ARM64_REG_LR))
                raise ValueError('Unknown TLS key')
            tls_values[(threads.current, a)] = b; result = 0
        elif name == 'pthread_once':
            if a in once_done:
                result = 0
            else:
                if any(control == a for control, _ in once_pending):
                    raise ValueError('Recursive pthread_once')
                once_pending.append((a, machine.reg_read(UC_ARM64_REG_LR)))
                machine.reg_write(UC_ARM64_REG_LR, once_return)
                machine.reg_write(UC_ARM64_REG_PC, b)
                return
        elif name == 'pthread_mutexattr_init':
            attributes[a] = 0; condition_attributes[a] = 0; machine.mem_write(a, bytes(4)); result = 0
        elif name == 'pthread_mutexattr_settype':
            if a not in attributes or b not in (0, 1, 2):
                raise ValueError('Unsupported mutex attributes')
            attributes[a] = b; result = 0
        elif name == 'pthread_mutexattr_destroy':
            attributes.pop(a, None); result = 0
        elif name == 'pthread_mutex_init':
            mutexes[a] = {'type': attributes.get(b, 0), 'depth': 0}; result = 0
        elif name in ('pthread_mutex_lock', 'pthread_mutex_unlock', 'pthread_mutex_destroy'):
            state = mutexes.setdefault(a, {'type': 0, 'depth': 0})
            if name == 'pthread_mutex_lock':
                if state['depth'] and state.get('owner') != threads.current:
                    threads.block('mutex', a)
                    return
                if state['depth'] and state['type'] != 1:
                    raise ValueError('Recursive non-recursive mutex')
                state['owner'] = threads.current
                state['depth'] += 1
            elif name == 'pthread_mutex_unlock':
                if not state['depth']:
                    raise ValueError('Unlock of unlocked mutex')
                if state.get('owner') != threads.current:
                    raise ValueError('Unlock by non-owner')
                state['depth'] -= 1
                if not state['depth']:
                    state['owner'] = None
                    threads.wake('mutex', a)
            else:
                if state['depth']:
                    raise ValueError('Destroy of locked mutex')
                del mutexes[a]
            result = 0
        elif name == 'pthread_rwlock_init':
            # No lock acquisitions are supported yet; stop at any actual use.
            machine.mem_write(a, bytes(56)); result = 0
        elif name == 'pthread_condattr_init':
            condition_attributes[a] = 0; attributes[a] = 0; machine.mem_write(a, bytes(4)); result = 0
        elif name == 'pthread_condattr_setclock':
            if a not in condition_attributes or b not in (0, 1):
                raise ValueError('Unsupported condition clock')
            condition_attributes[a] = b; result = 0
        elif name == 'pthread_condattr_destroy':
            condition_attributes.pop(a, None); result = 0
        elif name == 'pthread_cond_init':
            conditions.add(a); machine.mem_write(a, bytes(4)); result = 0
        elif name == 'pthread_cond_destroy':
            conditions.discard(a); result = 0
        else:
            report['stop_reason'] = 'unsupported_service'; report['required_import'] = name; report['caller'] = hex(machine.reg_read(UC_ARM64_REG_LR)); report['argument0'] = hex(a)
            if name == 'dlopen':
                report['requested_library'] = bytes(machine.mem_read(a, 256)).split(bytes([0]))[0].decode('utf8', errors='replace')
            machine.emu_stop(); return
        machine.reg_write(UC_ARM64_REG_X0, result)
        machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))

    anonymous_next = 0x50000000
    anonymous_maps = {}
    virtual_umask = 0o022
    filesystem = ProbeFilesystem()
    report['filesystem_events'] = filesystem.events

    def interrupt(machine, number, _):
        nonlocal anonymous_next, virtual_umask
        syscall = machine.reg_read(UC_ARM64_REG_X8)
        if number == 2 and syscall == 166:
            previous_mask = virtual_umask
            virtual_umask = machine.reg_read(UC_ARM64_REG_X0) & 0o777
            machine.reg_write(UC_ARM64_REG_X0, previous_mask)
            return
        if number == 2 and syscall == 167:
            option = machine.reg_read(UC_ARM64_REG_X0)
            suboption = machine.reg_read(UC_ARM64_REG_X1)
            address = machine.reg_read(UC_ARM64_REG_X2)
            size = machine.reg_read(UC_ARM64_REG_X3)
            if option == 0x53564d41 and suboption == 0 and anonymous_maps.get(address) == size:
                # PR_SET_VMA_ANON_NAME labels an existing allocation, not its contents.
                label_pointer = machine.reg_read(UC_ARM64_REG_X4)
                label = bytes(machine.mem_read(label_pointer, 80)).split(bytes([0]))[0].decode('utf8', errors='replace')
                report.setdefault('anonymous_mapping_labels', []).append({'address': hex(address), 'label': label})
                machine.reg_write(UC_ARM64_REG_X0, 0)
                return
        if number == 2 and syscall == 222:
            address = machine.reg_read(UC_ARM64_REG_X0)
            size = machine.reg_read(UC_ARM64_REG_X1)
            protection = machine.reg_read(UC_ARM64_REG_X2)
            flags = machine.reg_read(UC_ARM64_REG_X3)
            offset = machine.reg_read(UC_ARM64_REG_X5)
            if flags == 0x32 and address % 4096 == 0 and 0 < size <= 0x4000000 and protection in (0, 1, 3) and offset == 0:
                size = (size + 4095) & ~4095
                if any(base <= address and address + size <= base + length for base, length in anonymous_maps.items()):
                    # MAP_FIXED anonymous replacement within our own reservations.
                    machine.mem_protect(address, size, protection)
                    machine.mem_write(address, bytes(size))
                    machine.reg_write(UC_ARM64_REG_X0, address)
                    return
            if address == 0 and 0 < size <= 0x4000000 and flags == 0x22 and protection in (0, 1, 3) and offset == 0:
                size = (size + 4095) & ~4095
                if anonymous_next + size > 0x60000000:
                    machine.reg_write(UC_ARM64_REG_X0, (1 << 64) - 12)
                    return
                machine.mem_map(anonymous_next, size, protection)
                anonymous_maps[anonymous_next] = size
                report.setdefault('anonymous_mappings', []).append({'address': hex(anonymous_next), 'size': size})
                machine.reg_write(UC_ARM64_REG_X0, anonymous_next)
                anonymous_next += size
                return
        if number == 2 and syscall == 226:
            address = machine.reg_read(UC_ARM64_REG_X0)
            size = machine.reg_read(UC_ARM64_REG_X1)
            protection = machine.reg_read(UC_ARM64_REG_X2)
            if address % 4096 == 0 and size > 0 and protection in (0, 1, 3):
                size = (size + 4095) & ~4095
                if any(base <= address and address + size <= base + length for base, length in anonymous_maps.items()):
                    machine.mem_protect(address, size, protection)
                    machine.reg_write(UC_ARM64_REG_X0, 0)
                    return
        if number == 2 and syscall == 215:
            address = machine.reg_read(UC_ARM64_REG_X0)
            size = machine.reg_read(UC_ARM64_REG_X1)
            if anonymous_maps.get(address) == size:
                machine.mem_unmap(address, size)
                del anonymous_maps[address]
                machine.reg_write(UC_ARM64_REG_X0, 0)
                return
        if number == 2 and syscall in (34, 56, 79, 48, 57, 62, 63, 64, 80):
            a, b, c, d = [machine.reg_read(register) for register in (
                UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3)]
            path = None
            try:
                if syscall in (34, 56, 79, 48):
                    raw = bytearray()
                    for index in range(4096):
                        character = machine.mem_read(b + index, 1)[0]
                        if not character:
                            break
                        raw.append(character)
                    else:
                        raise ValueError('Filesystem path bound exceeded')
                    path = filesystem.path(raw.decode('utf8'), a)
                if syscall == 34:
                    result = filesystem.mkdir(path, c & ~virtual_umask)
                elif syscall == 56:
                    result = filesystem.open(path, c, d & ~virtual_umask)
                elif syscall == 79:
                    if d != 0:
                        raise NotImplementedError('fstatat flags')
                    machine.mem_write(c, filesystem.metadata(path)); result = 0
                elif syscall == 48:
                    result = filesystem.access(path, c)
                elif syscall == 80:
                    machine.mem_write(b, filesystem.metadata(filesystem.handle(a)[0])); result = 0
                elif syscall == 57:
                    result = filesystem.close(a)
                elif syscall == 62:
                    result = filesystem.seek(a, b - (1 << 64) if b & (1 << 63) else b, c)
                elif syscall in (63, 64):
                    if c > 0x100000:
                        raise ValueError('Filesystem transfer bound exceeded')
                    if syscall == 63:
                        data = filesystem.read(a, c)
                        machine.mem_write(b, data); result = len(data)
                    else:
                        result = filesystem.write(a, bytes(machine.mem_read(b, c)))
            except OSError as error:
                if error.errno == 2 and path:
                    report.setdefault('missing_files', []).append(path)
                result = -error.errno
            except NotImplementedError as error:
                report['stop_reason'] = 'unsupported_filesystem_operation'
                report['filesystem_error'] = str(error)
                machine.emu_stop()
                return
            machine.reg_write(UC_ARM64_REG_X0, result & ((1 << 64) - 1))
            return
        report['stop_reason'] = 'unsupported_syscall'
        report['syscall_number'] = syscall
        report['syscall_pc'] = hex(machine.reg_read(UC_ARM64_REG_PC))
        report['syscall_arguments'] = [hex(machine.reg_read(register)) for register in (
            UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
            UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5)]
        if syscall == 34:
            pointer = machine.reg_read(UC_ARM64_REG_X1)
            report['requested_directory'] = bytes(machine.mem_read(pointer, 256)).split(bytes([0]))[0].decode('utf8', errors='replace')
        machine.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.hook_add(UC_HOOK_INTR, interrupt)
    uc.reg_write(UC_ARM64_REG_X0, 0x1190000)  # Explicitly empty dependency table.
    uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
    uc.reg_write(UC_ARM64_REG_LR, sentinel)
    uc.reg_write(UC_ARM64_REG_TPIDR_EL0, 0x1180000)
    if bionic:
        # The supplied Bionic's uselocale accesses TLS_SLOT_THREAD_ID (1),
        # then its per-thread locale slot at offset 0xb00. Single probe thread.
        uc.mem_write(0x1180008, struct.pack('<Q', 0x1198000))
        uc.mem_write(0x1198b00, struct.pack('<Q', 0x1199000))
    report['initializers_completed'] = 0
    try:
        for name in ('libc++_shared.so', 'libamaploc.so', 'libloc_base.so', 'liblocation_kit.so', 'libamapmain.so') + (('libamapr.so', 'libamapnsq.so') if data_module else ()):
            elf, base = libraries[name]
            section = elf.get_section_by_name('.init_array')
            if section is None:
                continue
            for offset in range(0, section['sh_size'], 8):
                target = struct.unpack('<Q', uc.mem_read(base + section['sh_addr'] + offset, 8))[0]
                if target in (0, 0xffffffffffffffff):
                    continue
                report.pop('return_value', None)
                report['phase'] = f'initializer:{name}:{offset // 8}'
                report['stop_reason'] = 'instruction_or_time_limit'
                uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
                uc.reg_write(UC_ARM64_REG_LR, sentinel)
                threads.run(target, sentinel + 4, timeout=5000000, count=1000000)
                if report['stop_reason'] != 'returned_unverified':
                    return report
                report['initializers_completed'] += 1
        report['initializers_executed'] = True
        report['phase'] = 'thread_factory'
        report['stop_reason'] = 'instruction_or_time_limit'
        for register in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6):
            uc.reg_write(register, 0)
        uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
        uc.reg_write(UC_ARM64_REG_LR, sentinel)
        threads.run(libraries['libamapmain.so'][1] + 0xe05a0, sentinel + 4, timeout=5000000, count=1000000)
        if report['stop_reason'] != 'returned_unverified':
            return report
        report['thread_factory_pointer'] = report.pop('return_value')
        uc.mem_write(0x1190038, struct.pack('<Q', int(report['thread_factory_pointer'], 16)))
        if data_module:
            report['phase'] = 'data_module_create'
            report['stop_reason'] = 'instruction_or_time_limit'
            uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
            uc.reg_write(UC_ARM64_REG_LR, sentinel)
            threads.run(exports['_ZN4dice20data_createModulePtrEv'], sentinel + 4, timeout=5000000, count=1000000)
            if report['stop_reason'] != 'returned_unverified':
                return report
            report['data_module_pointer'] = report.pop('return_value')
            pointer = int(report['data_module_pointer'], 16)
            vtable = struct.unpack('<Q', uc.mem_read(pointer, 8))[0]
            # Original assembly config uses 0x160 bytes, with mode 0755 at +0x158.
            # Empty C++ strings deliberately describe the empty research filesystem.
            uc.mem_write(0x11c2000, bytes(0x160))
            uc.mem_write(0x11c2158, struct.pack('<I', 0x1ed))
            for phase, slot, argument in (
                ('data_module_configure', 0x140, 0x11c2000),
                ('data_module_start', 0xe8, 0),
            ):
                target = struct.unpack('<Q', uc.mem_read(vtable + slot, 8))[0]
                report['phase'] = phase
                report['stop_reason'] = 'instruction_or_time_limit'
                uc.reg_write(UC_ARM64_REG_X0, pointer)
                uc.reg_write(UC_ARM64_REG_X1, argument)
                uc.reg_write(UC_ARM64_REG_X2, 0)  # No completion observer in this probe.
                uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
                uc.reg_write(UC_ARM64_REG_LR, sentinel)
                threads.run(target, sentinel + 4, timeout=5000000, count=1000000)
                if report['stop_reason'] != 'returned_unverified':
                    return report
                report[phase + '_return_value'] = report.pop('return_value')
            getter = struct.unpack('<Q', uc.mem_read(vtable + 0x160, 8))[0]
            report['data_provider_sd_getter'] = hex(getter)
            report['phase'] = 'data_provider_sd_get'
            report['stop_reason'] = 'instruction_or_time_limit'
            uc.reg_write(UC_ARM64_REG_X0, pointer)
            uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
            uc.reg_write(UC_ARM64_REG_LR, sentinel)
            threads.run(getter, sentinel + 4, timeout=5000000, count=1000000)
            if report['stop_reason'] != 'returned_unverified':
                return report
            report['data_provider_sd_pointer'] = report.pop('return_value')
            if int(report['data_provider_sd_pointer'], 16) == 0:
                report['stop_reason'] = 'data_provider_not_initialized'
                report['required_next_step'] = 'Configure libamapr data module before requesting its SD provider'
                return report
        report['phase'] = 'factory'
        report['stop_reason'] = 'instruction_or_time_limit'
        uc.reg_write(UC_ARM64_REG_X0, 0x1190000)
        uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
        uc.reg_write(UC_ARM64_REG_LR, sentinel)
        threads.run(entry, sentinel + 4, timeout=5000000, count=1000000)
        if report['stop_reason'] == 'returned_unverified':
            report['factory_return_value'] = report.pop('return_value')
            report['phase'] = 'module_configure'
            report['stop_reason'] = 'instruction_or_time_limit'
            # Separate configuration table, not the factory's service table.
            # +0x28 is DicePosWorkPath*, shared by posEngine and locEngine.
            # Leave unknown dependencies absent rather than inventing objects.
            uc.mem_write(0x11c1000, bytes(0x58))
            if data_module:
                uc.mem_write(0x11c1018, struct.pack('<Q', int(report['data_provider_sd_pointer'], 16)))
            uc.reg_write(UC_ARM64_REG_X0, int(report['factory_return_value'], 16))
            uc.reg_write(UC_ARM64_REG_X1, 0x11c1000)
            uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
            uc.reg_write(UC_ARM64_REG_LR, sentinel)
            threads.run(libraries['liblocation_kit.so'][1] + 0x1ef28, sentinel + 4, timeout=5000000, count=1000000)
            if report['stop_reason'] != 'returned_unverified':
                return report
            report['module_configure_return_value'] = report.pop('return_value')
            report['configuration_dependencies_supplied'] = False
            report['phase'] = 'position_service_create'
            report['stop_reason'] = 'instruction_or_time_limit'
            # Fixed-sample native service factory, identified by its singleton write.
            uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
            uc.reg_write(UC_ARM64_REG_LR, sentinel)
            threads.run(libraries['libamaploc.so'][1] + 0x87fd98, sentinel + 4, timeout=5000000, count=1000000)
            if report['stop_reason'] == 'returned_unverified':
                report['service_create_return_value'] = report.pop('return_value')
                pointer = struct.unpack('<Q', uc.mem_read(libraries['libamaploc.so'][1] + 0xa542b0, 8))[0]
                report['position_service_pointer'] = hex(pointer)
                report['phase'] = 'module_start'
                report['stop_reason'] = 'instruction_or_time_limit'
                uc.reg_write(UC_ARM64_REG_X0, int(report['factory_return_value'], 16))
                uc.reg_write(UC_ARM64_REG_SP, 0x11f0000)
                uc.reg_write(UC_ARM64_REG_LR, sentinel)
                threads.run(libraries['liblocation_kit.so'][1] + 0x1f0c4, sentinel + 4, timeout=5000000, count=1000000)
    except (UcError, ValueError) as error:
        report['stop_reason'] = 'emulation_error'; report['error'] = str(error); report['pc'] = hex(uc.reg_read(UC_ARM64_REG_PC))
        if uc.reg_read(UC_ARM64_REG_PC) == libraries['libamaploc.so'][1] + 0x867280:
            factory = struct.unpack('<Q', uc.mem_read(libraries['libamaploc.so'][1] + 0xa543a8, 8))[0]
            report['file_factory_pointer'] = hex(factory)
            if factory == 0:
                report['missing_dependency'] = 'amap_app::IFileFactory'
                report['dependency_setter'] = 'posEngine::setFileFactory'
                report['dependency_evidence'] = 'get +0x88268c and set +0x8826d0 share global +0xa543a8'
        frame = uc.reg_read(UC_ARM64_REG_X29)
        report['native_backtrace'] = []
        seen_frames = set()
        for _ in range(24):
            if not frame or frame in seen_frames:
                break
            seen_frames.add(frame)
            try:
                frame, return_pc = struct.unpack('<QQ', uc.mem_read(frame, 16))
            except UcError:
                break
            report['native_backtrace'].append(hex(return_pc))
        report['syscall_number'] = uc.reg_read(UC_ARM64_REG_X8)
        if report['syscall_number'] == 56:
            address = uc.reg_read(UC_ARM64_REG_X1)
            try:
                report['requested_path'] = bytes(uc.mem_read(address, 256)).split(bytes([0]))[0].decode('utf8', errors='replace')
            except UcError:
                pass
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('--bionic', help='Optional real ARM64 Bionic libc for locale routines')
    parser.add_argument('--data-module', action='store_true', help='Probe the original libamapr data-module factory as well')
    args = parser.parse_args()
    print(json.dumps(probe(args.apk, args.bionic, args.data_module), indent=2))
