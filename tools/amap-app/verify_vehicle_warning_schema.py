"""Check the recovered warning schema/call chain in the pinned APK ELF.

This verifies disassembly evidence, not a successful ACCS session or live alert.
"""
import argparse
import hashlib
import io
import json
import zipfile

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile


LIB_SHA256 = "cc8bc29dfb2116e7d6289e0f5fcd613c5e76d8fc396dc9ceafd3436ade004684"
FIELDS = {
    0xc8bf74: ("bizType", 0xd85c6c),
    0xc8bfa0: ("bizData", 0xd85e3c),
    0xc968b4: ("metaInfo", 0xc960a8),
    0xc968e0: ("data", 0xc968f4),
    0xc93318: ("pushId", 0xd85e3c),
    0xc93334: ("pushType", 0xd85c6c),
    0xc93360: ("pushTime", 0xd85e3c),
    0xc96538: ("v2xSafe", 0xc96594),
    0xc96440: ("show", 0xc96458),
    0xc91968: ("sceneType", 0xd85e3c),
    0xc91984: ("warningLevel", 0xd85c6c),
    0xc919a0: ("curveMeet", 0xc91a18),
    0xc919bc: ("nodeMeet", 0xc91ae4),
    0xc919d8: ("sceneData", 0xd85e3c),
}
CALLS = {
    0x7c868c: 0x7c9e24,   # Scene push -> interactionHorus wrapper
    0x7c9e60: 0xc80278,  # Wrapper JSON parser
    0x7c9ea0: 0x7c9efc,  # bizData consumer
    0x7c9f44: 0xc81068,  # Warning body parser
    0xc810c0: 0xc968a0,
    0xc9610c: 0xc93304,  # metaInfo is push metadata, not pathId/traceId
    0xc96958: 0xc96524,
    0xc96550: 0xc96594,
    0xc965f8: 0xc96438,
    0xc964bc: 0xc91954,
}


def verify(apk):
    with zipfile.ZipFile(apk) as archive:
        data = archive.read("lib/arm64-v8a/libamaphorus.so")
    if hashlib.sha256(data).hexdigest() != LIB_SHA256:
        raise ValueError("warning schema verifier requires the pinned APK ELF")
    elf = ELFFile(io.BytesIO(data))
    segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]

    def read(address, size):
        segment = next(s for s in segments if
            s["p_vaddr"] <= address < s["p_vaddr"] + s["p_filesz"])
        offset = segment["p_offset"] + address - segment["p_vaddr"]
        return data[offset:offset + size]

    dis = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    for address, (name, consumer) in FIELDS.items():
        instructions = list(dis.disasm_lite(read(address, 40), address))
        first, second = instructions[:2]
        assert first[2] == "adrp" and second[2] == "add", hex(address)
        page = int(first[3].split("#")[1], 0)
        offset = int(second[3].split("#")[1], 0)
        assert read(page + offset, len(name) + 1) == name.encode() + b"\0", name
        assert any(m in ("bl", "b") and op == f"#{consumer:#x}"
                   for _, _, m, op in instructions), name
    for address, target in CALLS.items():
        instruction = next(dis.disasm_lite(read(address, 4), address))
        assert instruction[2:] == ("bl", f"#{target:#x}"), hex(address)
    return {"elfSha256": LIB_SHA256, "fieldsChecked": len(FIELDS),
            "callsChecked": len(CALLS), "liveTransportVerified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True)
    print(json.dumps(verify(parser.parse_args().apk)))
