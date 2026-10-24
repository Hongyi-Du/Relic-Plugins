"""Managed loopback OrganizationBench process, independent of research pilots."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .benchmark import Benchmarks, process_lock
from .store import OrgError


def start_server(store,source):
    source=Path(source).resolve()
    if not (source/'organizationbench/runtime.py').is_file():raise OrgError('Select the OrganizationBench repository containing organizationbench/runtime.py.')
    root=store.path.parent/'benchmarks'/'organizationbench'
    receipt=root/'server.json';root.mkdir(parents=True,exist_ok=True)
    with process_lock(root/'server.lock'):
        if receipt.exists():
            existing=json.loads(receipt.read_text(encoding='utf-8'))
            try:
                if existing['source']==str(source) and Benchmarks.request(existing['url'],'/health')['ok']:return existing
            except Exception:pass
        receipt.unlink(missing_ok=True)
        python=Path(sys.executable)
        if os.name=='nt' and python.with_name('pythonw.exe').exists():python=python.with_name('pythonw.exe')
        log=(root/'server.log').open('a',encoding='utf-8')
        script=Path(__file__).resolve().parents[1]/'scripts/organizationbench_server.py'
        proc=subprocess.Popen([str(python),'-X','utf8',str(script),'--source',str(source),'--root',str(root/'runs'),'--receipt',str(receipt)],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        log.close()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if receipt.exists():
                try:return json.loads(receipt.read_text(encoding='utf-8'))
                except ValueError:pass
            if proc.poll() is not None:raise OrgError('OrganizationBench failed to start; inspect '+str(root/'server.log'))
            time.sleep(.1)
        raise OrgError('OrganizationBench startup timed out; inspect '+str(root/'server.log'))


def create_run(service,org_id,source,workload='acmecloud_portfolio_v2',epochs=6,seed=42):
    org=service.store.get(org_id)
    if org['status']!='active':raise OrgError('Resume the organization first.')
    members=[org['leader']]+[i for i in org['members'] if i!=org['leader']]
    if not 1<=len(members)<=5:raise OrgError('Upstream workload currently supports 1 to 5 selected chats.')
    server=start_server(service.store,source)
    spec=Benchmarks.request(server['url'],'/v1/sessions',{'config':{'setting':'solo' if len(members)==1 else 'team',
        'seed':seed,'epochs':epochs,'split_information':True,'workload_id':workload}})
    actors={i:[] for i in members}
    if len(members)==3:
        actors[members[0]]=['agent-1','agent-5'];actors[members[1]]=['agent-2'];actors[members[2]]=['agent-3','agent-4']
    else:
        for n,row in enumerate(spec['roster']):actors[members[n%len(members)]].append(row['id'])
    binding=Benchmarks(service.store).connect(org_id,server['url'],spec['session_id'],actors)
    return {'binding':binding,'spec':spec,'server':server}
