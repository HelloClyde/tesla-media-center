"""Verify the consumer APK's road-switch command and observer forwarding.

Reads the actual APK scripts and runs the pinned native JSON consumer against
controlled JSON lookups / an observer. This does not run map matching, obtain
native parallel-road candidates, or connect the command to TMC.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile

from elftools.elf.elffile import ELFFile
from extract_spx_file import extract
from inspect_oajx import inspect
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
                                UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_TPIDR_EL0)


LOC_SHA256 = '52e24c0feba9dd2a154286f1d73c191ab330f1818e3a97ff7d95e4ac9d3e4a34'
PREFIX = 'amap_bundle_drive/'
COMMANDS = {'LocSwitchMainToSide': 0, 'LocSwitchSideToMain': 1,
            'LocSwitchUpBridgeToDownBridge': 2, 'LocSwitchDownBridgeToUpBridge': 3}
RESOURCES = {
    'actions': PREFIX + 'ajx_modules/amap_bundle_lib_drivecommon/src/util/PosActionInfoUtil.js',
    'base': PREFIX + 'ajx_modules/amap_bundle_lib_travel_to_external/src/tripMap/const/TripMapBaseActionType.js',
    'parallel': PREFIX + 'src/car/trip_navi_page/Components/navi_pro_view/middle_widget/TripNaviParallelRoadView.jsx.js',
    'overhead': PREFIX + 'src/car/trip_navi_page/Components/navi_pro_view/middle_widget/TripNaviOverHeadRoadView.jsx.js',
    'events': PREFIX + 'src/car/trip_navi_page/Event/TripNaviStateEyrieEventManager.js',
    'request': PREFIX + 'src/car/trip_navi_page/Utils/calc_route_logic/TripNaviRequestRouteLogicApi.js',
}


def verify_forwarding(native, switch_type):
    """libamaploc 0x480a60: JSON switchParallel/switchType -> observer +0x78."""
    elf = ELFFile(io.BytesIO(native))
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for segment in elf.iter_segments():
        if segment['p_type'] != 'PT_LOAD':
            continue
        address, size = segment['p_vaddr'], segment['p_memsz']
        start = address & ~4095
        uc.mem_map(start, (address - start + size + 4095) & ~4095)
        uc.mem_write(address, segment.data())
    heap, stack, stop = 0x2000000, 0x3000000, 0x4000000
    uc.mem_map(heap, 0x10000); uc.mem_map(stack, 0x10000); uc.mem_map(stop, 0x1000)
    owner, json_root, child, number, observers, observer, vtable = [heap + offset for offset in (0, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700)]
    callback = stop + 0x100
    uc.mem_write(owner + 0xf8, struct.pack('<QQ', observers, observers + 8))
    uc.mem_write(observers, struct.pack('<Q', observer))
    uc.mem_write(observer, struct.pack('<Q', vtable))
    uc.mem_write(vtable + 0x78, struct.pack('<Q', callback))
    uc.mem_write(number + 0x28, struct.pack('<I', switch_type))
    keys, forwarded = [], []

    def hook(machine, address, size, user):
        if address == 0x9f2de0:
            key = bytes(machine.mem_read(machine.reg_read(UC_ARM64_REG_X1), 32)).split(b'\0')[0].decode()
            keys.append(key)
            source = machine.reg_read(UC_ARM64_REG_X0)
            if (source, key) == (json_root, 'switchParallel'): result = child
            elif (source, key) == (child, 'switchType'): result = number
            else: raise ValueError('unexpected native JSON lookup')
            machine.reg_write(UC_ARM64_REG_X0, result)
            machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))
        elif address == callback:
            forwarded.append(machine.reg_read(UC_ARM64_REG_X1))
            machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))
        elif address == stop:
            machine.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM64_REG_X0, owner); uc.reg_write(UC_ARM64_REG_X1, json_root)
    uc.reg_write(UC_ARM64_REG_SP, stack + 0xff00); uc.reg_write(UC_ARM64_REG_LR, stop)
    uc.emu_start(0x480a60, stop, count=10000)
    if keys != ['switchParallel', 'switchType'] or forwarded != [switch_type]:
        raise ValueError('native switch command was not forwarded as expected')
    return forwarded[0]


def verify_parallel_property(native, prop, *, path_available=True, eligible=True):
    """Run AutoBL's real classifier; supply controlled path and link getters.

    This checks the property decision, not how native MM establishes eligibility.
    The availability gates are exercised separately and never assumed true in
    claims about actual native candidates.
    """
    elf = ELFFile(io.BytesIO(native))
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for segment in elf.iter_segments():
        if segment['p_type'] != 'PT_LOAD': continue
        address, size = segment['p_vaddr'], segment['p_memsz']
        start = address & ~4095
        uc.mem_map(start, (address - start + size + 4095) & ~4095)
        uc.mem_write(address, segment.data())
    heap, stack, stop = 0x2000000, 0x3000000, 0x4000000
    uc.mem_map(heap, 0x10000); uc.mem_map(stack, 0x10000); uc.mem_map(stop, 0x1000)
    path, segment, link, table, thread = [heap + offset for offset in (0, 0x200, 0x400, 0x600, 0x900)]
    gate, getter = stop + 0x100, stop + 0x108
    for obj in (path, segment, link): uc.mem_write(obj, struct.pack('<Q', table))
    uc.mem_write(table + 0x148, struct.pack('<Q', gate))
    uc.mem_write(table + 0xe8, struct.pack('<Q', getter))
    calls = []

    def hook(machine, address, size, user):
        results = {0x58374c: int(path_available), 0x583810: segment,
                   0x5838c0: link, gate: int(eligible), getter: prop & 0xFFFFFFFF}
        if address in results:
            calls.append(address)
            machine.reg_write(UC_ARM64_REG_X0, results[address])
            machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_LR))
        elif address == stop: machine.emu_stop()
        elif address == 0x4cce68:
            raise ValueError('unexpected name fallback for a classified native property')

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_ARM64_REG_X1, path); uc.reg_write(UC_ARM64_REG_X2, 0); uc.reg_write(UC_ARM64_REG_X3, 0)
    uc.reg_write(UC_ARM64_REG_TPIDR_EL0, thread)
    uc.reg_write(UC_ARM64_REG_SP, stack + 0xff00); uc.reg_write(UC_ARM64_REG_LR, stop)
    uc.emu_start(0x581db8, stop, count=2000)
    result = uc.reg_read(UC_ARM64_REG_X0)
    expected = 3 if not path_available else 0 if not eligible else 1 if prop in (1, 3, 6, 8) else 2
    if result != expected or (getter in calls) != (path_available and eligible):
        raise ValueError('native parallel-property branch mismatch')
    return result


def verify(apk_path, index_path):
    index = json.loads(Path(index_path).read_text(encoding='utf-8'))
    with zipfile.ZipFile(apk_path) as apk:
        container = apk.read('assets/ajx.bundle/bundles.oajx')
        native = apk.read('lib/arm64-v8a/libamaploc.so')
    digest = hashlib.sha256(native).hexdigest()
    if digest != LOC_SHA256:
        raise ValueError('road-switch verifier requires the pinned APK native library')
    bundles = inspect(container)['entries']
    scripts, hashes = {}, {}
    for key, resource in RESOURCES.items():
        matches = [(bundle['bundle_index'], item['raw_fields']) for bundle in index for item in bundle['files'] if item['name'] == resource]
        if len(matches) != 1: raise ValueError('APK script must resolve to one resource: ' + resource)
        payload = extract(container, bundles, *matches[0])
        scripts[key] = payload.decode('utf-8')
        hashes[key] = hashlib.sha256(payload).hexdigest()
    switches = {name: int(code) for name, code in re.findall(r'"(LocSwitch\w+)",\s*(-?\d+)', scripts['actions'])}
    if switches != {'LocSwitchNULL': -1, **COMMANDS}: raise ValueError('unexpected APK switch command table')
    required = {
        'actions': ['switchParallel:', 'switchType:', 'SUBMIT_OPERATE_TO_POS'],
        'base': ['SUBMIT_OPERATE_TO_POS: 83'],
        'parallel': ['actionSwitchParallel(t)', 'doParallelRoadReroute()'],
        'overhead': ['actionSwitchParallel(t)', 'doOverHeadRoadReroute()'],
        'events': ['onNaviEventTypeLocParallelRoadInfo(e)', 'e.flag', 'e.hwFlag'],
        'request': ['"CALCROUTEFORPARALLELROAD", 3', '"CALCROUTEFOROVERHEADROAD", 5'],
    }
    for key, values in required.items():
        for value in values:
            if value not in scripts[key]: raise ValueError('APK call-chain evidence missing: ' + value)
    forwarded = {name: verify_forwarding(native, code) for name, code in COMMANDS.items()}
    properties = {str(prop): verify_parallel_property(native, prop) for prop in (1, 3, 5, 6, 7, 8)}
    gates = {'noPath': verify_parallel_property(native, 7, path_available=False),
             'notEligible': verify_parallel_property(native, 7, eligible=False)}
    return {'nativeSha256': digest, 'scriptSha256': hashes, 'posAction': 83,
            'switchCommands': forwarded, 'calcActions': {'parallel': 3, 'overhead': 5},
            'nativeObserverForwardingVerified': True,
            'autoBLPropertyClassification': properties, 'autoBLAvailabilityGates': gates,
            'nativeCandidateSelectionVerified': False, 'tmcNativeSwitchIntegrated': False,
            'independentTunnelCommandInThisTable': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.apk, args.index), ensure_ascii=False, indent=2))
