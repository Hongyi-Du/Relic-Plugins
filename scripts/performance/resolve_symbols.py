"""Post-process retained CI native stacks after the measured process has exited."""
from __future__ import annotations

import argparse
import json
import ntpath
import os
from pathlib import Path
import struct
import subprocess
import urllib.parse
import urllib.request
import uuid


SYMBOL_SERVER = "https://msdl.microsoft.com/download/symbols"
TARGET_MODULES = {"dwrite", "d2d1", "microsoft.ui.xaml"}


def codeview_identity(data: bytes) -> tuple[str, str]:
    """Read the PE's actual RSDS identity; never choose symbols by DLL version."""
    def u16(offset: int) -> int:
        return struct.unpack_from("<H", data, offset)[0]

    def u32(offset: int) -> int:
        return struct.unpack_from("<I", data, offset)[0]

    if data[:2] != b"MZ":
        raise ValueError("Not a PE image")
    pe = u32(0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Missing PE signature")
    optional = pe + 24
    magic = u16(optional)
    if magic not in (0x10B, 0x20B):
        raise ValueError("Unknown PE optional header")
    directory = optional + (112 if magic == 0x20B else 96)
    debug_rva, debug_size = struct.unpack_from("<II", data, directory + 6 * 8)
    section_start = optional + u16(pe + 20)

    def file_offset(rva: int) -> int:
        for index in range(u16(pe + 6)):
            section = section_start + index * 40
            virtual_size, address, raw_size, raw_start = struct.unpack_from("<IIII", data, section + 8)
            if address <= rva < address + max(virtual_size, raw_size):
                return raw_start + rva - address
        raise ValueError("Debug directory is outside PE sections")

    debug = file_offset(debug_rva)
    for entry in range(debug, debug + debug_size, 28):
        if u32(entry + 12) != 2:  # IMAGE_DEBUG_TYPE_CODEVIEW
            continue
        size, _, offset = struct.unpack_from("<III", data, entry + 16)
        record = data[offset:offset + size]
        if len(record) < 25 or record[:4] != b"RSDS":
            continue
        guid = uuid.UUID(bytes_le=record[4:20]).hex.upper()
        age = struct.unpack_from("<I", record, 20)[0]
        name = ntpath.basename(record[24:].split(b"\0", 1)[0].decode("utf-8"))
        if not name.lower().endswith(".pdb"):
            raise ValueError("CodeView identity has no PDB filename")
        return name, guid + format(age, "X")
    raise ValueError("No RSDS CodeView identity in image")


def symbol_url(name: str, identity: str) -> str:
    return f"{SYMBOL_SERVER}/{urllib.parse.quote(name, safe='')}/{identity}/{urllib.parse.quote(name, safe='')}"


def resolve(executable: Path, output: Path) -> dict:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Symbol downloads and native resolution are CI-only")
    modules: dict[str, dict] = {}
    for source in sorted((output / "stacks").glob("native-stack-*.stdout.txt")):
        for line in source.read_text(encoding="utf-8").splitlines():
            frame = json.loads(line)
            if frame.get("kind") != "native_frame" or frame.get("module", "").lower() not in TARGET_MODULES:
                continue
            path = frame.get("image_name")
            if not path or not frame.get("module_offset"):
                continue
            module = modules.setdefault(path, {"image": path, "offsets": set(), "sources": set()})
            module["offsets"].add(frame["module_offset"])
            module["sources"].add(source.name)
    results = []
    for index, module in enumerate(modules.values()):
        result = {"image": module["image"], "offsets": sorted(module["offsets"], key=lambda n: int(n, 16)),
                  "sources": sorted(module["sources"])}
        results.append(result)
        try:
            name, identity = codeview_identity(Path(module["image"]).read_bytes())
            cache = (output / "symbol-cache" / str(index)).resolve()
            cache.mkdir(parents=True, exist_ok=True)
            result.update(pdb=name, codeview_identity=identity, source=symbol_url(name, identity))
            pdb = cache / name
            with urllib.request.urlopen(result["source"], timeout=60) as response, pdb.open("wb") as destination:
                while chunk := response.read(1024 * 1024):
                    destination.write(chunk)
            result["download_bytes"] = pdb.stat().st_size
            command = [str(executable), "--resolve", module["image"], str(cache), *result["offsets"]]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
            result.update(returncode=completed.returncode, stderr=completed.stderr,
                          symbols=[json.loads(line) for line in completed.stdout.splitlines() if line.strip()])
            result["unresolved_offsets"] = [item.get("module_offset") for item in result["symbols"]
                                              if not item.get("resolved")]
            if completed.returncode or len(result["symbols"]) != len(result["offsets"]):
                result["error"] = "Native resolver did not resolve every requested frame with a matched PDB"
        except Exception as error:
            result["error"] = str(error)
    report = {"source": "Actual captured module offsets resolved after native measurement and process shutdown",
              "acceptance_eligible": False, "original_stacks_modified": False, "modules": results}
    (output / "resolved-symbols.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = resolve(args.exe.resolve(), args.output.resolve())
    print(json.dumps({"modules": len(report["modules"]),
                      "errors": [item["error"] for item in report["modules"] if "error" in item]}))
