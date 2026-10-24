"""Host-owned black-box workflows. Product components cannot supply a verdict."""
import csv
from decimal import Decimal
import importlib
import io
import json
from pathlib import Path
import sys


def evaluate(directory):
    sys.path.insert(0,str(Path(directory).resolve()))
    api=importlib.import_module('api')
    results=[]; trace=[]
    def case(name,run):
        state={'entries':[],'grants':{'alpha':{'guest':True},'beta':{'guest':True}}}
        def call(operation='post',tenant='alpha',user='owner',**extra):
            r={'operation':operation,'tenant':tenant,'user':user,**extra}
            response=api.handle(state,r)
            trace.append({'case':name,'request':r,'response':response})
            return response
        def post(**kw):return call(operation_id=kw.pop('operation_id','op-1'),amount_cents=kw.pop('amount_cents',123),name=kw.pop('name','invoice'),**kw)
        try:run(call,post,state);results.append({'name':name,'passed':True})
        except Exception as e:results.append({'name':name,'passed':False,'error':type(e).__name__+': '+str(e)})
    def v2(c,p,s):
        r=p(schema='v2');assert r['status']==200 and isinstance(r['body']['id'],str)
        assert type(r['body']['amount_cents']) is int and r['body']['amount_cents']==123
    def legacy(c,p,s):
        r=p(schema='legacy');assert r['status']==200 and isinstance(r['body']['entry_id'],str)
        assert r['body']['amount_decimal']=='1.23'
    def retry(c,p,s):
        a=p();b=p();assert a==b
        r=c('list');assert r['status']==200 and len(r['body'])==1
    def conflict(c,p,s):
        a=p();b=p(amount_cents=456);assert b['status']==409
        assert c('list')['body'][0]['amount_cents']==123
    def tenants(c,p,s):
        a=p();b=p(tenant='beta');assert a['status']==b['status']==200
        assert len(c('list')['body'])==len(c('list',tenant='beta')['body'])==1
        assert a['body']['id']!=b['body']['id']
    def isolated(c,p,s):
        p(name='alpha-secret');p(tenant='beta',operation_id='b',name='beta-secret')
        assert 'beta-secret' not in json.dumps(c('list')['body'])
        assert 'alpha-secret' not in json.dumps(c('list',tenant='beta')['body'])
    def guest(c,p,s):
        p();r=c('list',user='guest');assert r['status']==200 and len(r['body'])==1
    def revoke(c,p,s):
        p();assert c('revoke',member='guest')['status']==200
        r=c('list',user='guest');assert r['status'] in (200,403) and r['body'] in ([],None)
    def csv_isolation(c,p,s):
        p(name='alpha-secret');p(tenant='beta',operation_id='b',name='beta-secret')
        r=c('export');assert r['status']==200 and 'alpha-secret' in r['body'] and 'beta-secret' not in r['body']
    def csv_revoke(c,p,s):
        p(name='alpha-secret');c('revoke',member='guest')
        r=c('export',user='guest');assert 'alpha-secret' not in str(r['body'])
    def csv_exact(c,p,s):
        p(amount_cents=1);r=c('export');rows=list(csv.DictReader(io.StringIO(r['body'])))
        assert rows[0]['amount_decimal']=='0.01' and rows[0]['entry_id']
    def csv_precision(c,p,s):
        cents=9007199254740993;p(amount_cents=cents)
        rows=list(csv.DictReader(io.StringIO(c('export')['body'])))
        assert Decimal(rows[0]['amount_decimal'])*100==cents
    def csv_formula(c,p,s):
        for i,name in enumerate(['=1+1','+SUM(1)','-2','@x']):p(operation_id=str(i),name=name)
        rows=list(csv.DictReader(io.StringIO(c('export')['body'])))
        assert all(r['name'].startswith("'") for r in rows)
    def csv_utf8(c,p,s):
        p(name='发票,含逗号\n第二行');rows=list(csv.DictReader(io.StringIO(c('export')['body'])))
        assert len(rows)==1 and rows[0]['name']=='发票,含逗号\n第二行'
    def post_permission(c,p,s):
        assert p(user='guest')['status']==403 and s['entries']==[]
    def revoke_permission(c,p,s):
        p();assert c('revoke',user='guest',member='guest')['status']==403
        assert len(c('list',user='guest')['body'])==1
    def invalid_amount(c,p,s):
        for amount in [True,1.2,'123',0,-1]:assert p(amount_cents=amount)['status']==400
        assert s['entries']==[]
    def unknown(c,p,s):assert c('unknown')['status']==400
    for name,run in [('v2_contract',v2),('legacy_contract',legacy),('idempotent_retry',retry),
        ('conflicting_retry_atomic',conflict),('tenant_idempotency_namespace',tenants),('list_tenant_isolation',isolated),
        ('guest_collaboration',guest),('immediate_guest_revoke',revoke),('csv_tenant_isolation',csv_isolation),
        ('csv_revocation',csv_revoke),('csv_exact_decimal',csv_exact),('csv_large_integer_precision',csv_precision),
        ('csv_formula_escape',csv_formula),('csv_utf8_quoting',csv_utf8),('owner_only_post',post_permission),
        ('owner_only_revoke',revoke_permission),('invalid_amount_no_mutation',invalid_amount),('unknown_operation',unknown)]:case(name,run)
    return {'checks':results,'passed':all(r['passed'] for r in results),'passed_count':sum(r['passed'] for r in results),
        'total':len(results),'workflows':trace}


if __name__=='__main__':
    first=evaluate(sys.argv[1]);second=evaluate(sys.argv[1])
    first['same_bundle_replay_matches']=first==second
    print(json.dumps(first,ensure_ascii=False))
