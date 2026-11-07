"""Read-only access to a Windows named shared memory block (standard library, ctypes).

Python's mmap would *create* a missing block and read zeros; OpenFileMappingW fails instead,
which tells us the game is not running. Used by every shared memory game (ACE, and later
AC, ACC, iRacing, AMS2 ...).
"""
import sys

FILE_MAP_READ = 0x0004

if sys.platform == "win32":
    import ctypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_wchar_p]
    _kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    _kernel32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
    _kernel32.MapViewOfFile.restype = ctypes.c_void_p
    _kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    class _MemoryInfo(ctypes.Structure):
        _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                    ("AllocationProtect", ctypes.c_uint32), ("PartitionId", ctypes.c_uint16),
                    ("RegionSize", ctypes.c_size_t), ("State", ctypes.c_uint32),
                    ("Protect", ctypes.c_uint32), ("Type", ctypes.c_uint32)]

    _kernel32.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MemoryInfo), ctypes.c_size_t]
    _kernel32.VirtualQuery.restype = ctypes.c_size_t


class SharedMemory:
    def __init__(self, name: str, size: int):
        if sys.platform != "win32":
            raise FileNotFoundError("shared memory needs Windows")
        handle = _kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
        if not handle:
            raise FileNotFoundError(name)
        view = _kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 0)   # 0 = the whole block
        if not view:
            _kernel32.CloseHandle(handle)
            raise OSError(ctypes.get_last_error(), "MapViewOfFile failed", name)
        info = _MemoryInfo()
        _kernel32.VirtualQuery(view, ctypes.byref(info), ctypes.sizeof(info))
        self.handle, self.view = handle, view
        # Never read past the block, even if the game publishes a smaller one than we expect.
        self.available = min(size, info.RegionSize or size)
        self.size = size

    def read(self) -> bytes:
        """`size` bytes; zero-padded if the game's block is smaller."""
        return ctypes.string_at(self.view, self.available).ljust(self.size, b"\0")

    def close(self) -> None:
        if self.view:
            _kernel32.UnmapViewOfFile(self.view)
            self.view = None
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None
