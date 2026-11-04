"""Small advisory lock compatibility layer for POSIX and Windows."""
import os
import time
if os.name != 'nt':
    from fcntl import flock, LOCK_EX, LOCK_NB, LOCK_UN
else:
    import msvcrt
    LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8
    def flock(file, flags):
        fd = file if isinstance(file, int) else file.fileno()
        while True:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK if flags & LOCK_UN else msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if flags & LOCK_UN: raise
                if flags & LOCK_NB: raise BlockingIOError('Tác vụ đang giữ khóa.') from exc
                time.sleep(.1)
