"""Build the Relic package for each platform from explicit release contents; never package caches or live stores."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SHARED = ('LICENSE','CHANGELOG.md','CONTRIBUTING.md','release.json')
SCRIPTS = ('install.py','doctor.py','open_app.py')
SKIP = {'__pycache__','.git','.DS_Store','.native-fixtures','.pytest_cache','.native-tmp'}
README = '''# Relic · Public Beta

[English user guide](docs/guide.en.md) · [中文完整指南](docs/guide.zh-CN.md)

Windows: `python -X utf8 scripts/install.py`

macOS: `bash install.command`

Then open the Relic App: `python -X utf8 scripts/open_app.py` (on Windows also the Relic shortcut on the desktop). The App runs members on your Claude Code and Codex and brings Relic into their sessions; the installer also adds the plugin to Claude Code and Codex, so your own sessions can join organizations too.

Requires Python 3.11+ and a signed-in Claude Code or Codex. Keep this folder after installation.

安装：Windows 运行 `python -X utf8 scripts/install.py`，macOS 运行 `bash install.command`。然后打开 Relic App：`python -X utf8 scripts/open_app.py`（Windows 桌面上也有 Relic 快捷方式）。App 用你的 Claude Code 和 Codex 运行成员，自己把 Relic 带进它们的会话；安装脚本也把插件加到 Claude Code 和 Codex，你自己的会话也能加入组织。需要 Python 3.11+ 和已登录的 Claude Code 或 Codex。安装后保留本目录。

macOS desktop auto-wake and ChatGPT relay are unavailable; use CLI peers or inbox. macOS 暂不支持桌面自动唤醒与 ChatGPT 转发，请使用 CLI 同伴或 inbox。

[Windows EN](docs/windows.en.md) · [Windows 中文](docs/windows.zh-CN.md) · [macOS EN](docs/macos.en.md) · [macOS 中文](docs/macos.zh-CN.md)
'''


def source_files():
    files = {}
    for top in ('.claude-plugin', '.agents', 'plugins'):
        for path in sorted((ROOT/top).rglob('*')):
            if path.is_file() and not (set(path.parts)&SKIP) and path.suffix not in ('.pyc','.pyo'):
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in sorted((ROOT/'docs').rglob('*')):
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in SHARED:
        files[name] = (ROOT/name).read_bytes()
    for name in SCRIPTS:
        files['scripts/'+name] = (ROOT/'scripts'/name).read_bytes()
    files['install.ps1'] = (ROOT/'install.ps1').read_bytes()
    files['install.command'] = (ROOT/'install.command').read_bytes()
    files['README.md'] = README.encode('utf-8')
    return files


def validate(files):
    for name,data in files.items():
        if any(x in name.lower() for x in ('.sqlite','.env','trajectories/','round2-workspaces/','docs/research/runs/')):
            raise ValueError(f'Private/runtime file in release: {name}')
        if name.endswith('.json'):
            json.loads(data.decode('utf-8-sig'))
        if name.endswith(('.py','.md','.json','.ps1','.command','.mjs')):
            text=data.decode('utf-8-sig')
            if re.search(r'18201|X:[/\\]codex\+|sbbbbbb|gh[pousr]_[A-Za-z0-9]{20,}',text):
                raise ValueError(f'Maintainer path or credential-like data: {name}')
            for key in re.findall(r'sk-[A-Za-z0-9_-]{20,}',text):
                if '/tests/' not in '/'+name or not key.startswith(('sk-TEST','sk-OLD','sk-MEM')):
                    raise ValueError(f'Credential-like data: {name}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    parser.add_argument('--platform',choices=('all','windows','macos'),default='all',help='Which packages to build')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    version=json.loads((ROOT/'release.json').read_text())['version']
    files=source_files()
    validate(files)
    assets=[]
    for system in [s for s in ('windows','macos') if args.platform in ('all',s)]:
        prefix=f'relic-{system}-v{version}'
        path=args.output/(prefix+('.zip' if system=='windows' else '.tar.gz'))
        if system=='windows':
            with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                for name,data in files.items():
                    info=zipfile.ZipInfo(prefix+'/'+name, date_time=(2026,10,24,0,0,0))
                    info.compress_type=zipfile.ZIP_DEFLATED
                    archive.writestr(info,data)
            with zipfile.ZipFile(path) as archive:
                if archive.testzip():
                    raise ValueError(f'Archive corruption: {path}')
        else:
            import gzip
            with path.open('wb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as zipped:
                with tarfile.open(fileobj=zipped,mode='w') as archive:
                    for name,data in files.items():
                        info=tarfile.TarInfo(prefix+'/'+name)
                        info.size=len(data)
                        info.mode=0o755 if name.endswith('.command') else 0o644
                        info.mtime=1792800000
                        archive.addfile(info,io.BytesIO(data))
        item={'name':path.name,'platform':system,'size':path.stat().st_size,
              'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'files':len(files)}
        assets.append(item)
        print(f'{path.name}: {item["size"]} bytes, {len(files)} files')
    (args.output/'SHA256SUMS.txt').write_text(''.join(f'{a["sha256"]}  {a["name"]}\n' for a in assets),encoding='utf-8')
    result=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    manifest={'release':version,'source_commit':result.stdout.strip() if result.returncode==0 else None,
              'assets':assets,'macos_note':'CLI/core beta; desktop auto-wake and ChatGPT relay unavailable.'}
    (args.output/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
