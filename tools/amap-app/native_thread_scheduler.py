"""Bounded cooperative execution of real ARM64 pthread entry points in Unicorn.

This is a research executor, not a host-thread bridge. Unknown synchronization
operations must remain unsupported by its caller. It never fabricates a worker
result or silently discards the supplied thread entry point.
"""
from collections import deque
import struct
import time
from unicorn.arm64_const import (
    UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_X0, UC_ARM64_REG_TPIDR_EL0,
)


class NativeThreads:
    def __init__(self, uc, report, worker_return=0x10c0000):
        self.uc = uc
        self.report = report
        self.worker_return = worker_return
        self.current = 0
        self.tasks = {}
        self.ready = deque()
        self.yielded = False
        self.next_id = 1

    def spawn(self, entry, argument):
        if self.next_id > 16:
            raise ValueError('Native worker limit exceeded')
        thread = self.next_id
        self.next_id += 1
        base = 0x6000000 + thread * 0x200000
        self.uc.mem_map(base, 0x200000)
        saved = self.uc.context_save()
        self.uc.reg_write(UC_ARM64_REG_PC, entry)
        self.uc.reg_write(UC_ARM64_REG_X0, argument)
        self.uc.reg_write(UC_ARM64_REG_SP, base + 0x1f0000)
        self.uc.reg_write(UC_ARM64_REG_LR, self.worker_return)
        self.uc.reg_write(UC_ARM64_REG_TPIDR_EL0, base)
        # Pinned Bionic TLS thread pointer and per-thread locale storage.
        self.uc.mem_write(base + 8, struct.pack('<Q', base + 0x1000))
        self.uc.mem_write(base + 0x1b00, struct.pack('<Q', base + 0x2000))
        self.tasks[thread] = {'context': self.uc.context_save(), 'state': 'ready', 'entry': entry, 'started': False}
        self.uc.context_restore(saved)
        self.ready.append(thread)
        self.report.setdefault('native_workers', []).append({'id': thread, 'entry': hex(entry), 'argument': hex(argument)})
        return thread

    def block(self, kind, address, deadline=None, realtime=False, bitset=0xffffffff):
        task = self.tasks[self.current]
        task.update(state='waiting', wait_kind=kind, wait_address=address,
                    deadline=deadline, realtime=realtime, bitset=bitset)
        self.yielded = True
        self.uc.emu_stop()

    def wake(self, kind, address, maximum=0x7fffffff, bitset=0xffffffff):
        count = 0
        for thread, task in self.tasks.items():
            if count >= maximum:
                break
            if task['state'] == 'waiting' and task['wait_kind'] == kind and task['wait_address'] == address and task['bitset'] & bitset:
                task['state'] = 'ready'
                self.ready.append(thread)
                count += 1
        return count

    def wake_timeouts(self):
        saved = self.uc.context_save()
        for thread, task in self.tasks.items():
            if task['state'] != 'waiting' or task.get('deadline') is None:
                continue
            now = time.time() if task['realtime'] else time.monotonic()
            if now < task['deadline']:
                continue
            self.uc.context_restore(task['context'])
            # libc syscall() reports -1 with thread-local errno, unlike raw SVC.
            self.uc.reg_write(UC_ARM64_REG_X0, 0xffffffffffffffff)
            self.uc.mem_write(self.uc.reg_read(UC_ARM64_REG_TPIDR_EL0) + 16, struct.pack('<I', 110))
            task['context'] = self.uc.context_save()
            task['state'] = 'ready'
            self.ready.append(thread)
        self.uc.context_restore(saved)

    def on_code(self, address):
        if address != self.worker_return:
            return False
        task = self.tasks[self.current]
        task['state'] = 'exited'
        task['result'] = self.uc.reg_read(UC_ARM64_REG_X0)
        self.report.setdefault('native_worker_exits', []).append(self.current)
        self.yielded = True
        self.uc.emu_stop()
        return True

    def run(self, entry, end, timeout=5000000, count=1000000):
        """Run a main-thread call and its workers within one bounded budget."""
        self.current = 0
        self.uc.reg_write(UC_ARM64_REG_PC, entry)
        self.tasks[0] = {'context': self.uc.context_save(), 'state': 'ready', 'started': True}
        self.ready.appendleft(0)
        deadline = time.monotonic() + timeout / 1000000
        consumed = 0
        main_done = None
        self.wake_timeouts()
        while self.ready and time.monotonic() < deadline and consumed < count:
            thread = self.ready.popleft()
            task = self.tasks[thread]
            if task['state'] != 'ready':
                continue
            self.current = thread
            self.uc.context_restore(task['context'])
            if not task['started']:
                task['started'] = True
                self.report.setdefault('native_workers_started', []).append(thread)
            self.yielded = False
            quantum = min(10000, count - consumed)
            self.uc.emu_start(self.uc.reg_read(UC_ARM64_REG_PC), end, timeout=100000, count=quantum)
            consumed += quantum
            task['context'] = self.uc.context_save()
            if self.yielded:
                self.wake_timeouts()
                continue
            if self.report['stop_reason'] == 'returned_unverified' and thread == 0:
                main_done = task['context']
                task['state'] = 'returned'
                # Return to the caller with native register state intact. Workers
                # stay runnable and execute during the next call or explicit drain.
                break
            if self.report['stop_reason'] != 'instruction_or_time_limit':
                return
            self.ready.append(thread)
        if main_done:
            self.current = 0
            self.uc.context_restore(main_done)
        elif not self.ready:
            self.report['stop_reason'] = 'native_threads_waiting'
