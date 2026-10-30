"""Build one pinned CPU-only SKP inspector on a Windows CI runner, never locally."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

from contract import (CHROMIUM_DEPS_URL, SKIA_REPOSITORY, SKIA_REVISION, browser_binding,
                      read_json, require_ci, selected_dependencies, write_json)
from source_contract import check_source_contract

GN_ARGS = " ".join((
    "is_debug=false is_official_build=false target_cpu=\"x64\"",
    "skia_enable_tools=false skia_enable_ganesh=false skia_enable_graphite=false",
    "skia_enable_pdf=false skia_enable_skottie=false skia_enable_svg=false skia_enable_precompile=false",
    "skia_use_icu=false skia_use_harfbuzz=false skia_use_fontations=false skia_use_dawn=false",
    "skia_use_expat=false skia_use_lua=false skia_use_wuffs=false skia_use_partition_alloc=false",
    "skia_use_libjpeg_turbo_decode=false skia_use_libjpeg_turbo_encode=false",
    "skia_use_jpeg_gainmaps=false",
    "skia_use_libwebp_decode=false skia_use_libwebp_encode=false",
    "skia_use_libpng_decode=true skia_use_libpng_encode=true skia_use_zlib=true",
))
TARGET = '''
# Independent Relic raw SKP inspector. Original Skia parser/decoder code is unchanged.
skia_executable("relic_skp_probe") {
  sources = [ "relic_skp_probe.cpp" ]
  deps = [ ":skia" ]
  configs = [ ":skia_private" ]
  check_includes = false
}
'''


def main() -> int:
    require_ci()
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True, help="New disposable RUNNER_TEMP subdirectory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise RuntimeError("Only a Windows runner matching this capture's typeface factory is supported")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"status": "started", "commands": [], "canonical_output": False, "errors": []}

    def run(command, cwd, env=None, timeout=900):
        item = {"argv": [str(s) for s in command], "cwd": str(cwd), "started_unix": time.time()}
        receipt["commands"].append(item)
        write_json(output / "build.json", receipt)
        log_path = output / f"build-command-{len(receipt['commands']):02}.log"
        item["log"] = log_path.name
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        item.update(exit_code=result.returncode, finished_unix=time.time())
        write_json(output / "build.json", receipt)
        if result.returncode:
            raise RuntimeError(f"Build command failed ({result.returncode}); see {log_path.name}")
        return log_path

    try:
        browser = read_json(args.case / "browser.json")
        with urllib.request.urlopen(CHROMIUM_DEPS_URL, timeout=60) as response:
            deps_bytes = response.read()
        deps_source = deps_bytes.decode("utf-8")
        receipt["source_binding"] = browser_binding(browser, deps_source)
        (output / "chromium.DEPS").write_bytes(deps_bytes)
        work = args.work.resolve()
        if work.exists():
            raise RuntimeError("Build work directory already exists; no stale checkout is reused or deleted")
        runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
        if not work.is_relative_to(runner_temp) or work == runner_temp:
            raise RuntimeError("Build work directory must be a new child of RUNNER_TEMP")
        work.mkdir(parents=True)
        source = work / "skia"
        source.mkdir()
        run(["git", "init", "--quiet"], source)
        run(["git", "fetch", "--depth=1", SKIA_REPOSITORY, SKIA_REVISION], source)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], source)
        actual_head = run(["git", "rev-parse", "HEAD"], source).read_text(encoding="utf-8").strip()
        receipt["actual_skia_checkout_revision"] = actual_head
        if actual_head != SKIA_REVISION:
            raise RuntimeError("Actual checked-out Skia revision differs from browser DEPS")
        source_contract = check_source_contract(source)
        write_json(output / "source-contract.json", source_contract)
        if source_contract["errors"]:
            raise RuntimeError("Actual pinned checkout does not satisfy the read-only source contract")
        official_deps = (source / "DEPS").read_text(encoding="utf-8")
        dependencies = selected_dependencies(official_deps)
        receipt["selected_official_dependencies"] = dependencies
        (output / "skia.DEPS").write_text(official_deps, encoding="utf-8")
        # The official sync tool supports GIT_SYNC_DEPS_PATH. Keep this in the checkout root
        # so its own fetch-gn path remains valid; every URL/revision comes from original DEPS.
        limited = source / "RELIC_SKP_DEPS"
        limited.write_text("deps = " + repr(dependencies) + "\n", encoding="utf-8")
        env = os.environ.copy()
        env.update(GIT_SYNC_DEPS_PATH=str(limited), GIT_SYNC_DEPS_SKIP_EMSDK="1")
        run([sys.executable, "tools/git-sync-deps"], source, env)
        receipt["actual_dependency_revisions"] = {}
        for name, url_revision in dependencies.items():
            head = run(["git", "rev-parse", "HEAD"], source / name).read_text(encoding="utf-8").strip()
            receipt["actual_dependency_revisions"][name] = head
            if head != url_revision.rsplit("@", 1)[1]:
                raise RuntimeError(f"Actual synced dependency differs from official DEPS: {name}")
        shutil.copyfile(Path(__file__).with_name("probe.cpp"), source / "relic_skp_probe.cpp")
        with (source / "BUILD.gn").open("a", encoding="utf-8") as build:
            build.write(TARGET)
        vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
        found = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                               capture_output=True, text=True, timeout=30, check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        vc = Path(found.stdout.strip()) / "VC"
        if not vc.is_dir():
            raise RuntimeError("CI runner has no installed VC compiler; this tool never installs one")
        gn_args = GN_ARGS + ' win_vc="' + vc.as_posix() + '"'
        receipt["gn_args"] = gn_args
        run([str(source / "bin/gn.exe"), "gen", "out/relic-skp", "--args=" + gn_args], source)
        ninja = shutil.which("ninja")
        if not ninja:
            candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "CMake/bin/ninja.exe"
            ninja = str(candidate) if candidate.is_file() else None
        if not ninja:
            raise RuntimeError("CI runner has no Ninja; provide the official runner build tool, not an unpinned download")
        run([ninja, "-C", "out/relic-skp", "relic_skp_probe"], source, timeout=1200)
        executable = source / "out/relic-skp/relic_skp_probe.exe"
        if not executable.is_file():
            raise RuntimeError("Build did not produce the requested executable")
        shutil.copyfile(executable, output / executable.name)
        receipt.update(status="built", executable=executable.name)
    except Exception as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
        receipt["status"] = "failed"
    finally:
        write_json(output / "build.json", receipt)
    return 0 if receipt["status"] == "built" else 1


if __name__ == "__main__":
    raise SystemExit(main())
