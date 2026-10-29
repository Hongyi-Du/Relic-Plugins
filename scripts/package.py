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
SCRIPTS = ('install.py','doctor.py','open_app.py','macos_app.py')
SKIP = {'__pycache__','.git','.DS_Store','.native-fixtures','.pytest_cache','.native-tmp'}
README = '''# Relic · Public Beta

This branch prepares the macOS Apple silicon prerelease based on v0.4.1-beta.1.
Use native arm64 Python 3.11+ and Node.js 22+. Desktop delivery is enabled only after its local capability checks pass.
The newer Windows release is maintained separately on the repository's main branch.

[English user guide](docs/guide.en.md) · [中文完整指南](docs/guide.zh-CN.md)

Windows: `python -X utf8 scripts/install.py`

macOS: `bash install.command`

Then open the Relic App: `python -X utf8 scripts/open_app.py` (on Windows also the Relic shortcut on the desktop). The App runs members on your Claude Code and Codex and brings Relic into their sessions; the installer also adds the plugin to Claude Code and Codex, so your own sessions can join organizations too.

Requires Python 3.11+ and a signed-in Claude Code or Codex. Keep this folder after installation.

安装：Windows 运行 `python -X utf8 scripts/install.py`，macOS 运行 `bash install.command`。然后打开 Relic App：`python -X utf8 scripts/open_app.py`（Windows 桌面上也有 Relic 快捷方式）。App 用你的 Claude Code 和 Codex 运行成员，自己把 Relic 带进它们的会话；安装脚本也把插件加到 Claude Code 和 Codex，你自己的会话也能加入组织。需要 Python 3.11+ 和已登录的 Claude Code 或 Codex。安装后保留本目录。

On macOS, check Settings → Harness connections or doctor.py --probe-desktop before using desktop delivery.
CLI/App-managed members and manual inbox work independently. macOS 桌面投递需先通过能力验证；CLI、App 内成员与手动 inbox 可独立使用。

[Windows EN](docs/windows.en.md) · [Windows 中文](docs/windows.zh-CN.md) · [macOS EN](docs/macos.en.md) · [macOS 中文](docs/macos.zh-CN.md)
'''

MACOS_README = '''# Relic for macOS · Apple silicon

macOS arm64 测试版源码安装包，基于 v0.4.1-beta.1。已完成真实 Claude Code + Codex 组织协作流程测试。
This macOS prerelease uses the tested v0.4.1 baseline; it does not include the newer v0.5/v0.6 Windows features.
Requires native arm64 Python 3.11+, Node.js 22+ with npm, and a signed-in Claude Code and/or Codex CLI.

## 安装 / Install

解压到固定目录，在 Terminal 进入该目录：
Extract into a permanent folder, then run from Terminal:

```sh
bash install.command --host none --open
```

安装器会创建 ~/Applications/Relic.app。以后可以从 Finder 打开；请保留解压目录。
The installer creates ~/Applications/Relic.app and opens Relic; keep the extracted folder in place.

进入 Settings → Harness connections，安装 ACP adapters，再选择 New organization → Add member → Run in the App。
Install the ACP adapters under Settings → Harness connections, then add members with Run in the App.
The adapters use your existing Claude/Codex login. Blank executable fields mean automatic discovery.

若需要让独立 CLI 会话加载插件，运行 `bash install.command --host both`，重启宿主并确认 hooks。
For independent CLI sessions, run `bash install.command --host both`, restart the hosts and review the hooks.

## 管理 / Manage

以下 python3 应为安装时使用的 arm64 Python 3.11+；也可以使用该解释器的完整路径。
Use the same native arm64 Python 3.11+ interpreter selected during installation for these commands.

```sh
python3 scripts/doctor.py
python3 scripts/open_app.py --status
python3 scripts/open_app.py --restart
python3 scripts/open_app.py --stop
```

关闭浏览器不会停止后台服务。组织数据默认保存在 ~/.relic；也可通过 RELIC_HOME 指定目录。
Closing the browser keeps the background server running. Organization data defaults to ~/.relic or RELIC_HOME.

此包不含个人聊天、账号凭据、本机 Python 绝对路径或已安装的依赖。桌面投递由本机能力检查控制。
This source package contains no personal chats, credentials, machine-specific launch paths or installed dependencies.
Desktop delivery is enabled only after local capability checks. This is an unsigned source installer prerelease.
Intel Macs and Rosetta runtimes are outside this release's support target.

[macOS 中文指南](docs/macos.zh-CN.md) · [macOS English guide](docs/macos.en.md)
'''


def portable_launch_config(files):
    """Normalize installer-generated machine paths in archive bytes, leaving the live install untouched."""
    def update(name, change):
        data = json.loads(files[name].decode('utf-8-sig'))
        change(data)
        files[name] = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')

    def mcp(data):
        for server in data['mcpServers'].values():
            server['command'] = 'python3'
            server['args'] = ['-X', 'utf8', './server.py']
            server.pop('env', None)

    def claude(data):
        data['mcpServers'] = {'org': {'command': 'python3',
                                    'args': ['-X', 'utf8', '${CLAUDE_PLUGIN_ROOT}/server.py']}}

    code = ("import os,runpy;runpy.run_path(os.path.join("
            "os.environ.get('CLAUDE_PLUGIN_ROOT') or os.environ['PLUGIN_ROOT'],"
            "'hooks','relic_hook.py'),run_name='__main__')")
    command = 'python3 -X utf8 -c "' + code + '"'

    def hooks(data):
        for groups in data.get('hooks', {}).values():
            for group in groups:
                for hook in group.get('hooks', []):
                    if hook.get('type') == 'command':
                        hook['command'] = command
                        hook.pop('args', None)

    update('plugins/relic/codex.mcp.json', mcp)
    update('plugins/relic/.claude-plugin/plugin.json', claude)
    for name in files:
        if name.startswith('plugins/relic/hooks/') and name.endswith('.json'):
            update(name, hooks)
    return files


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
    return portable_launch_config(files)


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
    parser.add_argument('--macos-format',choices=('tar.gz','zip','both'),default='tar.gz',
                        help='macOS archive format; ZIP keeps Unix executable permission metadata')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    release=json.loads((ROOT/'release.json').read_text())
    version=release['version']
    files=source_files()
    validate(files)
    assets=[]
    for system in [s for s in ('windows','macos') if args.platform in ('all',s)]:
        prefix=f'relic-{system}-v{version}'
        formats = ['zip'] if system == 'windows' else (['zip','tar.gz'] if args.macos_format == 'both' else [args.macos_format])
        contents = dict(files)
        if system == 'macos':
            contents['README.md'] = MACOS_README.replace('# Relic for macOS · Apple silicon',
                                                        '# Relic v' + version + ' · macOS Apple silicon').encode('utf-8')
        validate(contents)
        for format in formats:
            path=args.output/(prefix+'.'+format)
            if format == 'zip':
                with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                    for name,data in contents.items():
                        info=zipfile.ZipInfo(prefix+'/'+name, date_time=(2026,10,24,0,0,0))
                        info.create_system=3
                        info.external_attr=(0o100755 if name.endswith('.command') else 0o100644)<<16
                        info.compress_type=zipfile.ZIP_DEFLATED
                        archive.writestr(info,data)
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip():
                        raise ValueError(f'Archive corruption: {path}')
            else:
                import gzip
                with path.open('wb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as zipped:
                    with tarfile.open(fileobj=zipped,mode='w') as archive:
                        for name,data in contents.items():
                            info=tarfile.TarInfo(prefix+'/'+name)
                            info.size=len(data)
                            info.mode=0o755 if name.endswith('.command') else 0o644
                            info.mtime=1792800000
                            archive.addfile(info,io.BytesIO(data))
            item={'name':path.name,'platform':system,'size':path.stat().st_size,
                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'files':len(contents)}
            if system == 'macos':
                item['supported_architectures'] = ['arm64']
            assets.append(item)
            print(f'{path.name}: {item["size"]} bytes, {len(contents)} files')
    # LF on every platform: `sha256sum -c` reads a CR as part of the file name
    (args.output/'SHA256SUMS.txt').write_text(''.join(f'{a["sha256"]}  {a["name"]}\n' for a in assets),encoding='utf-8',
                                              newline='\n')
    result=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    dirty=subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True)
    manifest={'release':version,'source_commit':result.stdout.strip() if result.returncode==0 else None,
              'source_dirty':bool(dirty.stdout.strip()) if dirty.returncode==0 else None,
              'base_release':release.get('base_release'), 'plugin_version':release['plugin']['version'],
              'channel':release.get('channel', 'prerelease'),
              'assets':assets,'macos_note':'Apple silicon only; unsigned source installer prerelease. '
              'Desktop delivery is conditional on verified local host capabilities.'}
    (args.output/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':
    main()
