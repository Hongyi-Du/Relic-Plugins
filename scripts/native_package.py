"""Package an already compiled native client together with the one Python engine.

Called by package.py --native-build. Does not start the App or install anything.
"""
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import zipfile


def assemble(root, build, platform, output, files):
    root, build, output = Path(root), Path(build), Path(output)
    version = json.loads((root / "release.json").read_text(encoding="utf-8"))["version"]
    output.mkdir(parents=True, exist_ok=True)
    stage = output / ("relic-native-" + platform + "-v" + version)
    if stage.exists():
        raise ValueError("Use a fresh native output directory: " + str(stage))
    stage.mkdir()
    if platform == "windows":
        if not (build / "Relic.exe").is_file():
            raise ValueError("The WinUI publish directory must contain Relic.exe")
        shutil.copytree(build, stage, dirs_exist_ok=True)
        engine = stage
    else:
        binary = build / "Relic"
        if not binary.is_file():
            raise ValueError("The Swift release directory must contain Relic")
        app = stage / "Relic.app"
        executable = app / "Contents/MacOS/Relic"
        executable.parent.mkdir(parents=True)
        shutil.copy2(binary, executable)
        executable.chmod(0o755)
        engine = app / "Contents/Resources/engine"
        engine.mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "ai.hongyidu.relic", "CFBundleName": "Relic",
            "CFBundleDisplayName": "Relic", "CFBundleExecutable": "Relic",
            "CFBundlePackageType": "APPL", "CFBundleVersion": version.split("-")[0],
            "CFBundleShortVersionString": version.split("-")[0],
            "LSMinimumSystemVersion": "14.0", "LSArchitecturePriority": ["arm64"],
            "NSHighResolutionCapable": True,
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        }))
    for name, data in files.items():
        target = engine / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (stage / "README-native.md").write_bytes((root / "docs/native-install.md").read_bytes())
    # Native artifacts contain the original engine bytes, not a second port.
    for name, data in files.items():
        if (engine / name).read_bytes() != data:
            raise ValueError("Engine copy differs: " + name)
    archive_path = output / (stage.name + ".zip")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage.parent).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip():
            raise ValueError("Native archive is corrupt")
    print(archive_path)
    if platform == "windows":
        compiler = shutil.which("ISCC.exe") or str(Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"))
        if not Path(compiler).is_file():
            raise RuntimeError("Inno Setup 6 is required to build the per-user installer; the portable archive was assembled")
        subprocess.run([compiler, "/DSourceDir=" + str(stage.resolve()), "/DOutputDir=" + str(output.resolve()),
                        "/DAppVersion=" + version, str(root / "native/windows/installer.iss")], check=True)
    return archive_path
