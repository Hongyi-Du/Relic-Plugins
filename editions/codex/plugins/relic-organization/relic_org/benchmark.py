"""Outcome-based development tasks and a direct OrganizationBench transport."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

from .store import OrgError, gate, now, uid


COMPONENTS = ('api.py', 'ledger.py', 'policy.py')
BRIEFS = {
 'api.py': 'Customer/API responsibility: preserve legacy response entry_id and decimal amount strings; add v2 id and integer amount_cents. Export CSV must preserve all authorized rows and exact monetary values. Repeated same request must not duplicate charges; conflicting retry is 409. You own api.py, integrate through ledger and policy interfaces. Negotiate their interface and report tradeoffs to peers. Shared objective: a working tenant ledger, not personal task completion.',
 'ledger.py': 'Storage/engineering responsibility: integer cents only, tenant-scoped idempotency, conflicting retries must not mutate state. Same operation ID may be used independently by two tenants. You own ledger.py. API clients require two response schemas and decimal exports; clarify the interface with API and policy owners. Shared objective: a working tenant ledger.',
 'policy.py': 'Security/acceptance responsibility: tenant isolation must hold for both list and CSV; guests can read only while granted, owner revocation must take effect immediately. Owners of different tenants share the user name owner, which never permits crossing tenant boundaries. CSV formula cells need escaping. You own policy.py. Blanket denial of guests breaks promised customer collaboration; agree compatible interfaces with other owners. Shared objective: a working tenant ledger.'}

BASELINE = {
 'api.py': '''import csv,io\nimport ledger,policy\ndef handle(state,r):\n t=r['tenant']; u=r.get('user','owner'); op=r['operation']\n if op=='post':\n  row=ledger.post(state,t,r['operation_id'],r['amount_cents'],r.get('name',''))\n  return {'status':200,'body':{'id':row['id'],'amount_cents':row['amount_cents']}}\n if op=='revoke':\n  state['grants'].get(t,{}).pop(r['member'],None); return {'status':200,'body':{}}\n rows=[x for x in state['entries'] if policy.can_read(state,t,u,x)]\n if op=='list': return {'status':200,'body':rows}\n if op=='export':\n  s=io.StringIO(); w=csv.writer(s); w.writerow(['entry_id','amount_decimal','name'])\n  for x in rows:w.writerow([x['id'],str(x['amount_cents']/100),x['name']])\n  return {'status':200,'body':s.getvalue()}\n return {'status':400,'body':None}\n''',
 'ledger.py': '''def post(state,tenant,operation_id,amount_cents,name=''):\n for x in state['entries']:\n  if x['operation_id']==operation_id:return x\n row={'entry_id':len(state['entries'])+1,'tenant':tenant,'operation_id':operation_id,'amount_minor':amount_cents,'name':name}\n state['entries'].append(row); return row\n''',
 'policy.py': '''def can_read(state,tenant,user,row):\n return user=='owner' or bool(state['grants'].get(tenant,{}).get(user))\n'''}


def bundle_hash(files):
    return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@contextmanager
def process_lock(path):
    """Serialize cross-process adapter configuration and evaluator state."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
        if os.name=='nt':
            import msvcrt
            deadline=time.monotonic()+150
            while True:
                try: msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1); break
                except OSError:
                    if time.monotonic()>deadline:raise OrgError('Benchmark is busy; retry the same request.')
                    time.sleep(.05)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


class Benchmarks:
    def __init__(self,store):
        self.store=store
        self.root=store.path.parent/'benchmarks'

    def start(self,org_id,assignments):
        with self.store.transaction(org_id,'human','benchmark.started',{}) as (org,db):
            if org['status']!='active':raise OrgError('Resume organization before starting work.')
            if set(assignments)!=set(COMPONENTS) or set(assignments.values())-set(org['members']):
                raise OrgError('Assign all three components to selected members.')
            run={'id':uid('dev'),'kind':'tenant-ledger-v1','assignments':assignments,'files':dict(BASELINE),
                'revision':0,'contributions':{},'evaluations':[],'release':None,'started_at':now()}
            org.setdefault('benchmarks',{})[run['id']]=run
        return run

    def call(self,org_id,actor,operation,data):
        org=self.store.get(org_id,actor)
        if operation=='list':return list(org.get('benchmarks',{}).values())
        if org['status']!='active' and operation not in {'status','brief'}:raise OrgError('Organization is paused.')
        run=org.get('benchmarks',{}).get(data.get('run_id'))
        if not run:raise OrgError('Unknown organization benchmark.')
        if operation=='status':return run
        if operation=='brief':
            return {'run_id':run['id'],'objective':'Deliver a compatible, idempotent, isolated tenant ledger.',
                'components':[{ 'name':name,'brief':BRIEFS[name],'source':run['files'][name]}
                    for name,owner in run['assignments'].items() if owner==actor],
                'assignments':run['assignments'],'revision':run['revision'],'bundle_hash':bundle_hash(run['files']),
                'acceptance':'Host executes API workflows. handle(state,request) returns status/body; post/list/export/revoke. State has entries and grants. No earnings for meetings or protocols.',
                'caller':actor}
        if operation in {'submit','evaluate'}:
            verdict=gate(org,actor,'org_benchmark_'+operation,data)
            self.store.record_protocol_decision(org_id,actor,{**verdict,'source':'organization_benchmark','tool':'org_benchmark_'+operation})
            if not verdict['allowed']:raise OrgError('; '.join(verdict['reasons']))
        if operation=='submit':
            name=data['component']
            if run['assignments'].get(name)!=actor:raise OrgError('Only the component owner may submit it.')
            if not isinstance(data.get('content'),str):raise OrgError('Submit UTF-8 source content.')
            compile(data['content'],name,'exec')
            with self.store.transaction(org_id,actor,'benchmark.submitted',{'run_id':run['id'],'component':name}) as (fresh,db):
                current=fresh['benchmarks'][run['id']]
                if current['revision']!=data['expected_revision']:raise OrgError('Bundle revision conflict; read status and merge.')
                current['files'][name]=data['content']; current['revision']+=1
                current['contributions'][name]={'actor':actor,'revision':current['revision'],'at':now(),
                    'source_sha256':hashlib.sha256(data['content'].encode()).hexdigest()}
            return {'revision':current['revision'],'bundle_hash':bundle_hash(current['files'])}
        if operation=='evaluate':
            directory=self.root/run['id']
            with process_lock(directory/'evaluate.lock'):
                snapshot=self.store.get(org_id,actor)['benchmarks'][run['id']]
                digest=bundle_hash(snapshot['files'])
                target=directory/'bundles'/digest; target.mkdir(parents=True,exist_ok=True)
                for name,content in snapshot['files'].items():(target/name).write_text(content,encoding='utf-8')
                evaluator=Path(__file__).with_name('ledger_acceptance.py')
                output=subprocess.run([sys.executable,'-X','utf8',str(evaluator),str(target)],capture_output=True,
                    text=True,encoding='utf-8',timeout=45,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                if output.returncode!=0:raise OrgError('Host evaluator failed: '+output.stderr[-1000:])
                result=json.loads(output.stdout)
                result.update({'bundle_hash':digest,'revision':snapshot['revision'],'at':now(),'actor':actor,'bundle_path':str(target)})
                with self.store.transaction(org_id,actor,'benchmark.evaluated',{'run_id':run['id'],'passed':result['passed']}) as (fresh,db):
                    fresh['benchmarks'][run['id']]['evaluations'].append(result)
                (directory/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                return result
        if operation=='release':
            arguments={'run_id':run['id'],'bundle_hash':data['bundle_hash']}
            detail=dict(arguments)
            denial=None
            with self.store.transaction(org_id,actor,'benchmark.release_attempt',detail) as (fresh,db):
                verdict=gate(fresh,actor,'org_benchmark_release',arguments)
                current=fresh['benchmarks'][run['id']]
                detail.update({'allowed':verdict['allowed'],'protocol_ids':verdict['protocol_ids'],'action_hash':verdict['action_hash']})
                detail.update({k:v for k,v in verdict.items() if k not in detail})
                if not verdict['allowed']:
                    denial='; '.join(verdict['reasons']);detail['reasons']=verdict['reasons']
                else:
                    if bundle_hash(current['files'])!=data['bundle_hash']:raise OrgError('Bundle changed; evaluate and review current source.')
                    evidence=next((e for e in reversed(current['evaluations']) if e['bundle_hash']==data['bundle_hash'] and e['passed']),None)
                    if not evidence:raise OrgError('Release requires host acceptance of this exact bundle.')
                    if set(current['contributions'])!=set(COMPONENTS):raise OrgError('All three component owners must submit real contributions.')
                    current['release']={'bundle_hash':data['bundle_hash'],'actor':actor,'at':now(),'bundle_path':evidence['bundle_path']}
            if denial:raise OrgError(denial)
            return current['release']
        raise OrgError('Unsupported development benchmark operation.')

    def upstream(self,org_id,actor,operation,data):
        org=self.store.get(org_id,actor)
        if org['status']!='active' and operation=='invoke':raise OrgError('Organization is paused.')
        binding=org.get('organizationbench')
        if not binding:raise OrgError('Human must connect OrganizationBench from the native window first.')
        from urllib.parse import urlencode
        root='/v1/session?'+urlencode({'session_id':binding['session_id']})
        if operation=='catalog':return self.request(binding['url'],'/v1/tools?'+urlencode({'session_id':binding['session_id']}))
        if operation=='upstream_status':return self.request(binding['url'],root)['status']
        if operation=='export':return self.request(binding['url'],'/v1/export?'+urlencode({'session_id':binding['session_id']}))
        bench_actor=data.get('bench_actor') or binding['actors'][actor][0]
        if bench_actor not in binding['actors'].get(actor,[]):raise OrgError('Benchmark actor is not assigned to this chat.')
        if operation=='events':return self.request(binding['url'],'/v1/events?'+urlencode({'session_id':binding['session_id'],'actor':bench_actor,'cursor':data.get('cursor',0)}))
        if operation=='invoke':
            tool=data['tool']; arguments=data.get('arguments',{})
            verdict=gate(org,actor,'bench_'+tool,arguments)
            self.store.record_protocol_decision(org_id,actor,{**verdict,'source':'organizationbench_adapter','tool':'bench_'+tool})
            if not verdict['allowed']:raise OrgError('; '.join(verdict['reasons']))
            if not data.get('request_id'):raise OrgError('Stable request_id required; reuse it after uncertainty.')
            result=self.request(binding['url'],'/v1/tools/call',{'session_id':binding['session_id'],'actor':bench_actor,
                'tool':tool,'arguments':arguments,'request_id':data['request_id']})
            self.store.observe(org_id,actor,'benchmark.tool_result',{'tool':tool,'bench_actor':bench_actor,
                'ok':result.get('ok'),'request_id':data['request_id']})
            return result
        raise OrgError('Unsupported OrganizationBench operation.')

    @staticmethod
    def request(url,path,value=None):
        # Human-controlled loopback harness; never an external credentials endpoint.
        if not url.startswith('http://127.0.0.1:'):raise OrgError('OrganizationBench URL must be local loopback.')
        body=json.dumps(value,ensure_ascii=False).encode() if value is not None else None
        request=urllib.request.Request(url+path,data=body,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=150) as response:return json.load(response)

    def connect(self,org_id,url,session_id,actors):
        spec=self.request(url,'/v1/session?session_id='+session_id)['spec']
        with self.store.transaction(org_id,'human','organizationbench.connected',{'session_id':session_id}) as (org,db):
            if set(actors)!=set(org['members']):raise OrgError('Map every selected chat explicitly.')
            assigned=[a for values in actors.values() for a in values]
            if len(set(assigned))!=len(assigned) or set(assigned)!={a['id'] for a in spec['roster']}:raise OrgError('Map each benchmark actor exactly once.')
            org['organizationbench']={'url':url,'session_id':session_id,'actors':actors,'workload_id':spec['workload_id']}
        return org['organizationbench']
