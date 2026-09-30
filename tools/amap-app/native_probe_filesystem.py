"""Small in-memory POSIX filesystem for the offline ARM64 probe.

No host paths, network resources, or map contents are supplied implicitly.
Unsupported operations raise rather than pretending to succeed.
"""
import errno
import posixpath
import stat
import struct


class ProbeFilesystem:
    def __init__(self):
        self.nodes = {'/': (stat.S_IFDIR | 0o755, bytearray())}
        self.handles = {}
        self.next_fd = 100
        self.events = []

    def path(self, name, dirfd):
        if not name:
            raise OSError(errno.ENOENT, 'Empty path')
        if not name.startswith('/') and dirfd & 0xffffffff != 0xffffff9c:
            raise NotImplementedError('Relative directory descriptors')
        return posixpath.normpath('/' + name.lstrip('/'))

    def mkdir(self, path, mode):
        if path in self.nodes:
            raise OSError(errno.EEXIST, path)
        parent = self.nodes.get(posixpath.dirname(path))
        if parent is None:
            raise OSError(errno.ENOENT, path)
        if not stat.S_ISDIR(parent[0]):
            raise OSError(errno.ENOTDIR, path)
        if len(self.nodes) >= 1024:
            raise OSError(errno.ENOSPC, path)
        self.nodes[path] = (stat.S_IFDIR | (mode & 0o777), bytearray())
        self.events.append({'mkdir': path})
        return 0

    def metadata(self, path):
        if path not in self.nodes:
            raise OSError(errno.ENOENT, path)
        mode, content = self.nodes[path]
        # Linux asm-generic stat, used by ARM64 Bionic: 128 bytes.
        result = bytearray(128)
        struct.pack_into('<QQIIIIQQqIIq', result, 0, 1,
                         list(self.nodes).index(path) + 1, mode, 1, 1000, 1000,
                         0, 0, len(content), 4096, 0, (len(content) + 511) // 512)
        return bytes(result)

    def access(self, path, mode):
        self.metadata(path)
        permissions = self.nodes[path][0] >> 6 & 7
        if mode & ~7:
            raise OSError(errno.EINVAL, path)
        if mode & permissions != mode:
            raise OSError(errno.EACCES, path)
        return 0

    def open(self, path, flags, mode):
        if flags & ~(3 | 0x40 | 0x80 | 0x200 | 0x400 | 0x80000):
            raise NotImplementedError(f'Open flags {flags:#x}')
        if flags & 3 == 3:
            raise OSError(errno.EINVAL, path)
        if path not in self.nodes:
            if not flags & 0x40:
                raise OSError(errno.ENOENT, path)
            parent = self.nodes.get(posixpath.dirname(path))
            if parent is None:
                raise OSError(errno.ENOENT, path)
            if not stat.S_ISDIR(parent[0]):
                raise OSError(errno.ENOTDIR, path)
            if len(self.nodes) >= 1024:
                raise OSError(errno.ENOSPC, path)
            self.nodes[path] = (stat.S_IFREG | (mode & 0o777), bytearray())
        elif flags & 0x40 and flags & 0x80:
            raise OSError(errno.EEXIST, path)
        else:
            self.access(path, (4, 2, 6)[flags & 3])
        if stat.S_ISDIR(self.nodes[path][0]):
            raise OSError(errno.EISDIR, path)
        if flags & 0x200:
            if not flags & 3:
                raise OSError(errno.EACCES, path)
            self.nodes[path][1].clear()
        if len(self.handles) >= 128:
            raise OSError(errno.EMFILE, path)
        fd = self.next_fd
        self.next_fd += 1
        self.handles[fd] = [path, 0, flags]
        self.events.append({'open': path, 'fd': fd})
        return fd

    def handle(self, fd):
        if fd not in self.handles:
            raise OSError(errno.EBADF, str(fd))
        return self.handles[fd]

    def read(self, fd, count):
        handle = self.handle(fd)
        if handle[2] & 3 == 1:
            raise OSError(errno.EBADF, str(fd))
        result = bytes(self.nodes[handle[0]][1][handle[1]:handle[1] + count])
        handle[1] += len(result)
        return result

    def write(self, fd, data):
        handle = self.handle(fd)
        if handle[2] & 3 == 0:
            raise OSError(errno.EBADF, str(fd))
        content = self.nodes[handle[0]][1]
        offset = len(content) if handle[2] & 0x400 else handle[1]
        end = offset + len(data)
        if end > 0x100000 or sum(len(node[1]) for node in self.nodes.values()) + max(0, end - len(content)) > 0x1000000:
            raise OSError(errno.ENOSPC, handle[0])
        if end > len(content):
            content.extend(bytes(end - len(content)))
        content[offset:end] = data
        handle[1] = end
        return len(data)

    def seek(self, fd, offset, whence):
        handle = self.handle(fd)
        if whence not in (0, 1, 2):
            raise OSError(errno.EINVAL, str(fd))
        position = (0, handle[1], len(self.nodes[handle[0]][1]))[whence] + offset
        if position < 0:
            raise OSError(errno.EINVAL, str(fd))
        handle[1] = position
        return position

    def close(self, fd):
        self.handle(fd)
        del self.handles[fd]
        return 0
