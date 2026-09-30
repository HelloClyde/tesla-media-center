import struct
import unittest
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_SP, UC_ARM64_REG_LR
from native_thread_scheduler import NativeThreads


class NativeThreadExecutionTest(unittest.TestCase):
    def test_two_arm64_workers_actually_update_shared_memory(self):
        uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc.mem_map(0x10000, 0x40000)
        report = {'stop_reason': 'instruction_or_time_limit'}
        scheduler = NativeThreads(uc, report, worker_return=0x30000)
        # Worker: load counter, increment, store, return. Main waits for both.
        worker = [0xb9400001, 0x11000421, 0xb9000001, 0xd2800000, 0xd65f03c0]
        main = [0xb9400001, 0x7100083f, 0x54ffffc1, 0xd65f03c0]
        uc.mem_write(0x10000, struct.pack('<5I', *worker))
        uc.mem_write(0x11000, struct.pack('<4I', *main))
        scheduler.spawn(0x10000, 0x20000)
        scheduler.spawn(0x10000, 0x20000)

        def hook(machine, address, size, _):
            if scheduler.on_code(address):
                return
            if address == 0x30004:
                report['stop_reason'] = 'returned_unverified'
                machine.emu_stop()

        uc.hook_add(UC_HOOK_CODE, hook)
        uc.reg_write(UC_ARM64_REG_X0, 0x20000)
        uc.reg_write(UC_ARM64_REG_SP, 0x4f000)
        uc.reg_write(UC_ARM64_REG_LR, 0x30004)
        scheduler.run(0x11000, 0x30008)
        self.assertEqual(struct.unpack('<I', uc.mem_read(0x20000, 4))[0], 2)
        self.assertEqual(report['native_workers_started'], [1, 2])
        self.assertEqual(report['native_worker_exits'], [1, 2])
        self.assertEqual(report['stop_reason'], 'returned_unverified')


if __name__ == '__main__':
    unittest.main()
