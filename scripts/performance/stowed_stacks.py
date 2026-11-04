"""CI only: name the stacks WinUI stowed before failing fast.

A layout cycle (AG_E_LAYOUT_CYCLE) ends the app with 0xC000027B and stows the
error plus one warning context per element invalidated in the last passes,
each with the stack that invalidated it. The default crash analysis prints
only the first. This reads them all from a full dump, resolves native frames
with cdb and the Microsoft symbol server and managed frames with SOS !ip2md,
and counts which methods appear across the warnings.

Usage: python -X utf8 stowed_stacks.py --dump X.dmp --cdb CDB [--sos SOS.DLL] --output FILE"""
import argparse
import collections
import os
import re
import struct
import subprocess
import sys

if os.environ.get("GITHUB_ACTIONS") != "true":
    sys.exit("stowed_stacks.py runs on GitHub Actions only")

parser = argparse.ArgumentParser()
parser.add_argument("--dump", required=True)
parser.add_argument("--cdb", required=True)
parser.add_argument("--sos")
parser.add_argument("--output", required=True)
args = parser.parse_args()

data = open(args.dump, "rb").read()
sig, _ver, nstreams, dir_rva = struct.unpack_from("<4sIII", data, 0)
if sig != b"MDMP":
    sys.exit("Not a minidump")
streams = collections.defaultdict(list)
for i in range(nstreams):
    stype, size, rva = struct.unpack_from("<III", data, dir_rva + 12 * i)
    streams[stype].append((size, rva))

modules = []
for _size, rva in streams[4]:
    for i in range(struct.unpack_from("<I", data, rva)[0]):
        off = rva + 4 + 108 * i
        base, img_size, _cs, _ts, name_rva = struct.unpack_from("<QIIII", data, off)
        n = struct.unpack_from("<I", data, name_rva)[0]
        name = data[name_rva + 4:name_rva + 4 + n].decode("utf-16-le", "replace").split("\\")[-1]
        modules.append((base, base + img_size, name))
modules.sort()

ranges = []
for _size, rva in streams[5]:
    for i in range(struct.unpack_from("<I", data, rva)[0]):
        start, dsize, drva = struct.unpack_from("<QII", data, rva + 4 + 16 * i)
        ranges.append((start, dsize, drva))
for _size, rva in streams[9]:
    count, cur = struct.unpack_from("<QQ", data, rva)
    for i in range(count):
        start, dsize = struct.unpack_from("<QQ", data, rva + 16 + 16 * i)
        ranges.append((start, dsize, cur))
        cur += dsize
ranges.sort()


def read(addr, n):
    for start, dsize, drva in ranges:
        if start <= addr and addr + n <= start + dsize:
            return data[drva + addr - start: drva + addr - start + n]
    return None


def module_of(addr):
    for lo, hi, name in modules:
        if lo <= addr < hi:
            return lo, name
    return None, None


def is_managed(base):
    head = read(base, 0x40)
    if not head or head[:2] != b"MZ":
        return False
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    opt = read(base + pe + 24, 0xE8)
    return bool(opt) and struct.unpack_from("<H", opt, 0)[0] == 0x20B and struct.unpack_from("<I", opt, 0xE0)[0] != 0


exception = None
for _size, rva in streams[6]:
    code = struct.unpack_from("<I", data, rva + 8)[0]
    nparams = struct.unpack_from("<I", data, rva + 8 + 24)[0]
    params = struct.unpack_from("<15Q", data, rva + 8 + 32)
    exception = (code, params[:nparams])
if not exception or exception[0] != 0xC000027B or len(exception[1]) < 2:
    sys.exit("The dump's exception is not a stowed exception")

stowed = []
array, count = exception[1][0], exception[1][1]
for k in range(count):
    pointer = read(array + 8 * k, 8)
    raw = read(struct.unpack("<Q", pointer)[0], 56) if pointer else None
    if not raw:
        continue
    hr, form_thread = struct.unpack_from("<II", raw, 8)
    frames = []
    if form_thread & 3 == 1:
        word_size, words, trace = struct.unpack_from("<IIQ", raw, 24)
        block = read(trace, word_size * words) or b""
        frames = [struct.unpack_from("<Q", block, w * 8)[0] for w in range(len(block) // 8)]
    stowed.append((hr, frames))

managed_bases = {}
unique = []
for _hr, frames in stowed:
    for addr in frames:
        if addr not in unique:
            unique.append(addr)

script = [".symfix c:\\symcache", ".reload"]
if args.sos and os.path.exists(args.sos):
    script.append(".load " + args.sos)
for i, addr in enumerate(unique):
    base, name = module_of(addr)
    script.append(".echo ##%d" % i)
    if base is None or managed_bases.setdefault(base, is_managed(base)):
        script.append("!ip2md 0x%x" % addr if args.sos else "ln 0x%x" % addr)
    else:
        script.append("ln 0x%x" % addr)
script.append("q")
command_file = args.output + ".cdb.txt"
with open(command_file, "w", encoding="ascii") as f:
    f.write("\n".join(script) + "\n")
result = subprocess.run([args.cdb, "-z", args.dump, "-cf", command_file], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=900)
names = {}
current = None
for line in result.stdout.splitlines():
    marker = re.match(r"##(\d+)$", line.strip())
    if marker:
        current = int(marker.group(1))
        continue
    if current is None or current in names:
        continue
    method = re.search(r"Method Name:\s+(.+)", line)
    symbol = re.search(r"\)\s+([\w.]+![^|]+?)\s*(\||$)", line)
    if method:
        names[current] = method.group(1).strip()
    elif symbol:
        names[current] = symbol.group(1).strip()


def label(addr):
    base, name = module_of(addr)
    resolved = names.get(unique.index(addr))
    where = "%s+0x%x" % (name, addr - base) if base is not None else "0x%x" % addr
    return "%s  %s" % (where, resolved or "")


counts = collections.Counter()
with open(args.output, "w", encoding="utf-8") as out:
    out.write("%d stowed exceptions; %d unique frames\n" % (len(stowed), len(unique)))
    for k, (hr, frames) in enumerate(stowed):
        out.write("\n[%d] HRESULT 0x%08X, %d frames\n" % (k, hr & 0xFFFFFFFF, len(frames)))
        for addr in frames[:60]:
            out.write("    " + label(addr) + "\n")
        seen = set()
        for addr in frames:
            resolved = names.get(unique.index(addr), "")
            if resolved.startswith("Relic.") and resolved not in seen:
                seen.add(resolved)
                counts[resolved] += 1
    out.write("\nRelic methods by the number of stowed stacks they appear in:\n")
    for method, n in counts.most_common(40):
        out.write("  %3d  %s\n" % (n, method))
    out.write("\ncdb exit %d\n%s\n" % (result.returncode, result.stderr[-2000:]))
print(open(args.output, encoding="utf-8").read()[-6000:])
