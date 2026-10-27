import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_all_six_archives_extract_and_configure_without_host_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'archives'
            subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/package.py'),'--output',str(target)],
                           check=True,capture_output=True)
            manifest=json.loads((target/'release-manifest.json').read_text())
            self.assertEqual(len(manifest['assets']),6)
            for item in manifest['assets']:
                with self.subTest(asset=item['name']):
                    archive=target/item['name']
                    dest=Path(temp)/'Unpacked 空格'/item['platform']/item['edition']
                    dest.mkdir(parents=True)
                    if archive.suffix=='.zip':
                        with zipfile.ZipFile(archive) as package:
                            self.assertTrue(all('..' not in Path(n).parts for n in package.namelist()))
                            package.extractall(dest)
                    else:
                        with tarfile.open(archive) as package:
                            self.assertTrue(all(not m.issym() and not m.islnk() for m in package.getmembers()))
                            self.assertTrue(all('..' not in Path(m.name).parts for m in package.getmembers()))
                            launcher=next(m for m in package.getmembers() if m.name.endswith('/install.command'))
                            self.assertEqual(launcher.mode,0o755)
                            package.extractall(dest,filter='data')
                    extracted=next(dest.iterdir())
                    command=[sys.executable,'-X','utf8',str(extracted/'scripts/install.py'),'--configure-only']
                    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=20)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('No plugin was installed',result.stdout)
                    self.assertEqual(json.loads((extracted/'edition.json').read_text())['edition'],item['edition'])
                    bridge=item['edition']=='bridge'
                    self.assertEqual((extracted/'scripts/open_app.py').is_file(),bridge)
                    self.assertEqual((extracted/'plugins/relic/app/static/index.html').is_file(),bridge)
                    self.assertNotIn(b'\r', (extracted/'install.command').read_bytes())


if __name__=='__main__':
    unittest.main()
