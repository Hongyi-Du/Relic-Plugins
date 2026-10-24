"""Start the unmodified upstream environment in an isolated local run directory."""
import argparse
import json
import os
from pathlib import Path
import sys

p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--root',required=True);p.add_argument('--receipt',required=True)
a=p.parse_args();sys.path.insert(0,str(Path(a.source).resolve()))
from organizationbench.runtime import RunManager
from organizationbench.server import make_server
server=make_server(RunManager(a.root),host='127.0.0.1',port=0)
Path(a.receipt).write_text(json.dumps({'url':'http://127.0.0.1:'+str(server.server_port),'pid':os.getpid(),
    'source':str(Path(a.source).resolve()),'run_root':str(Path(a.root).resolve())}),encoding='utf-8')
try:server.serve_forever()
finally:server.server_close()
