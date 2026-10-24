"""Build six source packages from explicit release contents; never package caches or live stores."""
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
SCRIPTS = ('install.py','doctor.py','open_panel.py')
SKIP = {'__pycache__','.git','.DS_Store','.native-fixtures','.pytest_cache'}


def source_files(edition):
    base = ROOT/'editions'/edition
    files = {}
    for path in sorted(base.rglob('*')):
        if path.is_file() and not (set(path.parts)&SKIP) and path.suffix not in ('.pyc','.pyo'):
            files[path.relative_to(base).as_posix()] = path.read_bytes()
    for path in sorted((ROOT/'docs').rglob('*')):
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in SHARED:
        files[name] = (ROOT/name).read_bytes()
    for name in SCRIPTS:
        files['scripts/'+name] = (ROOT/'scripts'/name).read_bytes()
    files['install.ps1'] = (ROOT/'install.ps1').read_bytes()
    files['install.command'] = (ROOT/'install.command').read_bytes()
    files['edition.json'] = (json.dumps({'edition':edition})+'\n').encode()
    files['README.md'] = (f'# Relic {edition.title()} · Public Beta\n\n'
        '[English user guide](docs/guide.en.md) · [中文完整指南](docs/guide.zh-CN.md)\n\n'
        'Windows: `python -X utf8 scripts/install.py`\n\n'
        'macOS: `bash install.command`\n\n'
        'Requires Python 3.11+ and the signed-in host CLI. Keep this folder after installation. '
        'Review and trust hooks in the host. Enable one Relic edition per host.\n\n'
        '需要 Python 3.11+ 与已经登录的宿主 CLI。安装后保留本目录，在宿主审阅并信任 hooks。'
        '同一宿主只启用一个 Relic 版本。\n\n'
        'Bridge macOS desktop auto-wake and ChatGPT relay are unavailable; use CLI peers or inbox. '
        'macOS Bridge 暂不支持桌面自动唤醒与 ChatGPT 转发，请使用 CLI 同伴或 inbox。\n\n'
        '[Windows EN](docs/windows.en.md) · [Windows 中文](docs/windows.zh-CN.md) · '
        '[macOS EN](docs/macos.en.md) · [macOS 中文](docs/macos.zh-CN.md)\n').encode('utf-8')
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
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    version=json.loads((ROOT/'release.json').read_text())['version']
    assets=[]
    for edition in ('claude','codex','bridge'):
        files=source_files(edition)
        validate(files)
        for system in ('windows','macos'):
            prefix=f'relic-{edition}-{system}-v{version}'
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
            item={'name':path.name,'edition':edition,'platform':system,'size':path.stat().st_size,
                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'files':len(files)}
            assets.append(item)
            print(f'{path.name}: {item["size"]} bytes, {len(files)} files')
    (args.output/'SHA256SUMS.txt').write_text(''.join(f'{a["sha256"]}  {a["name"]}\n' for a in assets),encoding='utf-8')
    result=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    manifest={'release':version,'source_commit':result.stdout.strip() if result.returncode==0 else None,
              'assets':assets,'macos_note':'CLI/core beta; Bridge desktop auto-wake and ChatGPT relay unavailable.'}
    (args.output/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
