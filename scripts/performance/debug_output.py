"""CI only: keep the debug output (OutputDebugString) of Relic.exe while the
scenarios run. With RELIC_LAYOUT_CYCLE_TRACING=1 the app turns on WinUI's
layout cycle tracing, which writes each layout pass and every element whose
size kept changing there and nowhere else.

Usage: python -X utf8 debug_output.py --output FILE --stop FILE [--limit-mib N]
Runs until the stop file exists (or the output reaches the limit)."""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

import psutil

if os.environ.get("GITHUB_ACTIONS") != "true":
    sys.exit("debug_output.py runs on GitHub Actions only")

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--stop", required=True)
parser.add_argument("--limit-mib", type=float, default=40)
args = parser.parse_args()

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateEventW.restype = wt.HANDLE
k32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
k32.CreateFileMappingW.restype = wt.HANDLE
k32.CreateFileMappingW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR]
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
k32.SetEvent.argtypes = [wt.HANDLE]
k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
k32.WaitForSingleObject.restype = wt.DWORD

buffer_ready = k32.CreateEventW(None, False, False, "DBWIN_BUFFER_READY")
data_ready = k32.CreateEventW(None, False, False, "DBWIN_DATA_READY")
mapping = k32.CreateFileMappingW(wt.HANDLE(-1), None, 0x04, 0, 4096, "DBWIN_BUFFER")
view = k32.MapViewOfFile(mapping, 0x0004, 0, 0, 4096) if mapping else None
if not (buffer_ready and data_ready and view):
    sys.exit("Cannot open the debug output buffer: error %d" % ctypes.get_last_error())

names = {}
limit = int(args.limit_mib * 1048576)
written = kept = other = 0
with open(args.output, "w", encoding="utf-8", newline="\n") as out:
    out.write("# OutputDebugString lines from Relic.exe; columns: unix time, pid, text\n")
    k32.SetEvent(buffer_ready)
    while not os.path.exists(args.stop) and written < limit:
        if k32.WaitForSingleObject(data_ready, 500) != 0:
            continue
        pid = ctypes.c_uint32.from_address(view).value
        text = ctypes.string_at(view + 4).decode("mbcs", "replace").rstrip("\r\n")
        k32.SetEvent(buffer_ready)
        if pid not in names:
            try:
                names[pid] = psutil.Process(pid).name().lower()
            except psutil.Error:
                names[pid] = "?"
        if names[pid] != "relic.exe":
            other += 1
            continue
        line = "%.3f %d %s\n" % (time.time(), pid, text)
        out.write(line)
        written += len(line)
        kept += 1
    out.write("# kept %d lines from Relic.exe, skipped %d from other processes%s\n"
              % (kept, other, ", stopped at the size limit" if written >= limit else ""))
