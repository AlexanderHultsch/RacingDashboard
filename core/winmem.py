"""Read-only access to a Windows named shared memory block (standard library, ctypes).

Python's mmap would *create* a missing block and read zeros; OpenFileMappingW fails instead,
which tells us the game is not running. Used by every shared memory game (ACE, Assetto Corsa
Rally, iRacing, and later AC, ACC, AMS2 ...).
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
    """size: the bytes read() returns (zero-padded if the block is smaller); 0 = the whole block, as
    big as the game made it (iRacing), read in parts with read_at()."""

    def __init__(self, name: str, size: int = 0):
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
        self.available = min(size, info.RegionSize or size) if size else info.RegionSize
        self.size = size or self.available

    def read(self) -> bytes:
        """`size` bytes; zero-padded if the game's block is smaller."""
        return ctypes.string_at(self.view, self.available).ljust(self.size, b"\0")

    def read_at(self, offset: int, length: int) -> bytes:
        """`length` bytes from `offset`; zero-padded where they would lie past the block."""
        if offset < 0 or length <= 0 or offset >= self.available:
            return b"\0" * max(0, length)
        return ctypes.string_at(self.view + offset, min(length, self.available - offset)).ljust(length, b"\0")

    def close(self) -> None:
        if self.view:
            _kernel32.UnmapViewOfFile(self.view)
            self.view = None
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None


def process_running(*names: str) -> bool:
    """True if a process with one of these executable names runs (case-insensitive). For games that share
    block names (AC1, ACC and Assetto Corsa Rally all publish Local\\acpmf_*): the process tells them apart.
    Always False off Windows."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    snapshot_fn = _kernel32.CreateToolhelp32Snapshot
    snapshot_fn.argtypes, snapshot_fn.restype = [wintypes.DWORD, wintypes.DWORD], ctypes.c_void_p
    first, nxt = _kernel32.Process32FirstW, _kernel32.Process32NextW
    first.argtypes = nxt.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    wanted = {name.lower() for name in names}
    snapshot = snapshot_fn(0x2, 0)                       # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        ok = first(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in wanted:
                return True
            ok = nxt(snapshot, ctypes.byref(entry))
        return False
    finally:
        _kernel32.CloseHandle(snapshot)
