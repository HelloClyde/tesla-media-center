"""Research-only wrapper for the pinned APK's AOS string body codec.

Runs isolated ARM64 code from the locally supplied library. Do not use in the
TMC server process or treat a successful round trip as a valid navigation
session.
"""
import io
import struct
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, pkcs7
from unicorn import Uc, UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM
from unicorn.arm64_const import (
    UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_SP,
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
)


def transform(value: str | bytes, address: int, asset_dir: Path | None = None) -> str | bytes:
    root = asset_dir or Path(__file__).resolve().parents[2] / ".local-data/amap-app"
    data = (root / "libserverkey.so").read_bytes()
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x40000)
    uc.mem_write(0, data[:0x1000])
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 54)
    for i in range(phnum):
        typ, _flags, offset, va, _pa, size, _memsz, _align = struct.unpack_from(
            "<IIQQQQQQ", data, phoff + i * phentsize
        )
        if typ == 1:
            uc.mem_write(va, data[offset:offset + size])

    shoff = struct.unpack_from("<Q", data, 40)[0]
    shentsize, shnum = struct.unpack_from("<HH", data, 58)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shentsize) for i in range(shnum)]
    symsection = next(s for s in sections if s[1] == 11)
    strsection = sections[symsection[6]]
    strings = data[strsection[4]:strsection[4] + strsection[5]]
    symbols = []
    for offset in range(symsection[4], symsection[4] + symsection[5], 24):
        name_offset = struct.unpack_from("<I", data, offset)[0]
        symbols.append(strings[name_offset:strings.index(b"\0", name_offset)].decode())

    uc.mem_map(0x100000, 0x1000000)
    hooks = {}
    stub = 0x110000
    for section in sections:
        if section[1] != 4:
            continue
        for offset in range(section[4], section[4] + section[5], 24):
            target, info, addend = struct.unpack_from("<QQq", data, offset)
            symidx = info >> 32
            if info & 0xffffffff == 1027:
                uc.mem_write(target, struct.pack("<Q", addend))
            elif symidx:
                hooks[stub] = symbols[symidx]
                uc.mem_write(target, struct.pack("<Q", stub))
                stub += 4
    vm, vtable, env, envtable = 0x120000, 0x121000, 0x122000, 0x123000
    for obj, table, kind in ((vm, vtable, "vm"), (env, envtable, "jni")):
        uc.mem_write(obj, struct.pack("<Q", table))
        for index in range(240):
            hooks[stub] = (kind, index)
            uc.mem_write(table + 8 * index, struct.pack("<Q", stub))
            stub += 4
    staged_certificate = root / "signing-certificate.rsa"
    if staged_certificate.is_file():
        certificate_data = staged_certificate.read_bytes()
    else:
        # Legacy local research layout. Production stages just this certificate,
        # the pinned native library and other small verified assets, not the APK.
        with zipfile.ZipFile(root / "amap-release.apk") as archive:
            cert_name = next(n for n in archive.namelist() if n.startswith("META-INF/") and n.endswith(".RSA"))
            certificate_data = archive.read(cert_name)
    cert = pkcs7.load_der_pkcs7_certificates(certificate_data)[0].public_bytes(Encoding.DER)
    assert sum(b if b < 128 else b - 256 for b in cert) == 0x3576
    cert_ptr, input_ptr = 0x140000, 0x150000
    uc.mem_write(cert_ptr, cert)
    input_bytes = value.encode() if isinstance(value, str) else value
    if len(input_bytes) > 1 << 20:
        raise ValueError("oversized codec input")
    uc.mem_write(input_ptr, input_bytes + b"\0")
    hooks[0x33b8] = "signature-source"
    heap = 0x200000
    result = []
    registers = (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3)

    def cstr(pointer):
        output = bytearray()
        for i in range(1 << 20):
            byte = uc.mem_read(pointer + i, 1)[0]
            if not byte:
                return bytes(output)
            output.append(byte)
        raise ValueError("oversized string")

    def on_code(engine, address, _size, _userdata):
        nonlocal heap
        if address == 0x130000:
            engine.emu_stop()
            return
        if address not in hooks:
            return
        name = hooks[address]
        x0, x1, x2, x3 = (engine.reg_read(register) for register in registers)
        output = 0
        if name == "signature-source":
            output = 0x141000
        elif name == ("jni", 173):
            output = 0x142000
        elif name == ("jni", 35):
            output = 0x143000
        elif name == ("jni", 184):
            output = input_ptr if x1 == 0x155000 else cert_ptr
        elif name == ("jni", 171):
            output = len(input_bytes) if x1 == 0x155000 else len(cert)
        elif name == ("jni", 169):
            output = input_ptr
        elif name == ("jni", 167):
            result.append(cstr(x1))
            output = 0x156000
        elif name == ("jni", 176):
            output = 0x156000
        elif name == ("jni", 208):
            if x3 > 1 << 20:
                raise ValueError("oversized codec output")
            source = engine.reg_read(UC_ARM64_REG_X4)
            result.append(bytes(engine.mem_read(source, x3)))
        elif name in ("malloc", "_Znam"):
            output = heap
            heap += (x0 + 15) & ~15
        elif name in ("memcpy", "strncpy"):
            engine.mem_write(x0, bytes(engine.mem_read(x1, x2)))
            output = x0
        elif name == "memset":
            engine.mem_write(x0, bytes([x1 & 255]) * x2)
            output = x0
        elif name in ("strlen", "__strlen_chk"):
            output = len(cstr(x0))
        elif name == "__strrchr_chk":
            position = cstr(x0).rfind(bytes([x1 & 255]))
            output = x0 + position if position >= 0 else 0
        elif name == ("vm", 6):
            engine.mem_write(x1, struct.pack("<Q", env))
        elif name in (("jni", 6), ("jni", 33), ("jni", 113)):
            output = 0x125000
        elif name in ("free", "_ZdaPv", "__cxa_atexit", "__cxa_finalize", "__android_log_print", ("jni", 23), ("jni", 170), ("jni", 192)):
            pass
        else:
            raise RuntimeError(f"unsupported import {name} at {engine.reg_read(UC_ARM64_REG_LR):#x}")
        engine.reg_write(UC_ARM64_REG_X0, output)
        engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_LR))

    uc.hook_add(UC_HOOK_CODE, on_code)
    uc.reg_write(UC_ARM64_REG_SP, 0x1000000)
    uc.reg_write(UC_ARM64_REG_X0, env)
    uc.reg_write(UC_ARM64_REG_X2, 0x155000)
    uc.reg_write(UC_ARM64_REG_LR, 0x130000)
    uc.emu_start(address, 0x130004, count=1000000)
    if len(result) != 1:
        raise ValueError("encoder returned no string")
    return result[0] if isinstance(value, bytes) else result[0].decode()


def encode(value: str, asset_dir: Path | None = None) -> str:
    return transform(value, 0x8e64, asset_dir)


def decode(value: str, asset_dir: Path | None = None) -> str:
    return transform(value, 0x95c0, asset_dir)


def encode_binary(value: bytes, asset_dir: Path | None = None) -> bytes:
    """Call the APK's `amapEncodeBinaryV2` JNI routine (0x9980) in isolation."""
    return transform(value, 0x9980, asset_dir)


if __name__ == "__main__":
    encoded = encode('{"probe":1}')
    print({"input_bytes": len('{"probe":1}'.encode()), "output_bytes": len(encoded.encode()),
           "changed": encoded != '{"probe":1}', "round_trip": decode(encoded) == '{"probe":1}'})
