import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from relic_org.benchmark import Benchmarks, BASELINE, bundle_hash
from relic_org.store import Store, OrgError


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'org.sqlite3')
        self.org=self.store.create('test',[{'thread_id':i,'host_id':'local','title':i,'workspace':self.temp.name} for i in ['a','b','c']],'a')
        self.bench=Benchmarks(self.store)
        self.run=self.bench.start(self.org['id'],{'api.py':'a','ledger.py':'b','policy.py':'c'})

    def test_baseline_real_workflows_fail_and_replay(self):
        result=self.bench.call(self.org['id'],'a','evaluate',{'run_id':self.run['id']})
        self.assertFalse(result['passed']);self.assertEqual(result['total'],18)
        self.assertTrue(result['same_bundle_replay_matches'])
        self.assertTrue(Path(result['bundle_path'],'api.py').is_file())

    def test_ownership_revision_and_pause(self):
        args={'run_id':self.run['id'],'component':'api.py','content':BASELINE['api.py'],'expected_revision':0}
        with self.assertRaises(OrgError):self.bench.call(self.org['id'],'b','submit',args)
        self.bench.call(self.org['id'],'a','submit',args)
        with self.assertRaises(OrgError):self.bench.call(self.org['id'],'a','submit',args)
        self.store.human_control(self.org['id'],'pause')
        with self.assertRaises(OrgError):self.bench.call(self.org['id'],'a','evaluate',{'run_id':self.run['id']})
        self.assertEqual(self.bench.call(self.org['id'],'a','status',{'run_id':self.run['id']})['revision'],1)

    def test_paused_upstream_results_remain_readable_without_running_actions(self):
        with self.store.transaction(self.org['id'],'human','fixture',{}) as (org,db):
            org['organizationbench']={'url':'http://127.0.0.1:1','session_id':'fixture','actors':{'a':['agent-1'],'b':['agent-2'],'c':['agent-3']}}
        self.store.human_control(self.org['id'],'pause')
        with patch.object(Benchmarks,'request',return_value={'status':{'finished':True}}) as request:
            self.assertTrue(self.bench.upstream(self.org['id'],'a','upstream_status',{})['finished'])
            self.bench.upstream(self.org['id'],'a','export',{})
            self.bench.upstream(self.org['id'],'a','events',{})
            self.assertEqual(request.call_count,3)
            with self.assertRaisesRegex(OrgError,'paused'):
                self.bench.upstream(self.org['id'],'a','invoke',{'tool':'observe','arguments':{},'request_id':'one'})
            self.assertEqual(request.call_count,3)

    def test_release_requires_actual_evidence_all_owners_and_current_bundle(self):
        args={'run_id':self.run['id'],'bundle_hash':bundle_hash(self.run['files'])}
        with self.assertRaises(OrgError):self.bench.call(self.org['id'],'a','release',args)
        with self.store.transaction(self.org['id'],'human','fixture',{}) as (org,db):
            r=org['benchmarks'][self.run['id']]
            r['evaluations']=[{'bundle_hash':args['bundle_hash'],'passed':True,'bundle_path':'fixture'}]
        with self.assertRaises(OrgError):self.bench.call(self.org['id'],'a','release',args)
        with self.store.transaction(self.org['id'],'human','fixture',{}) as (org,db):
            org['benchmarks'][self.run['id']]['contributions']={k:{'actor':v} for k,v in self.run['assignments'].items()}
            org['benchmarks'][self.run['id']]['files']['api.py']+='\n# changed\n'
        with self.assertRaises(OrgError):self.bench.call(self.org['id'],'a','release',args)

    def test_adopted_rule_really_blocks_release_before_any_publication(self):
        args={'run_id':self.run['id'],'bundle_hash':bundle_hash(self.run['files'])}
        with self.store.transaction(self.org['id'],'human','fixture',{}) as (org,db):
            org['protocols']['p']={'id':'p','title':'peer review','status':'active','rules':[{'tools':['org_benchmark_release'],'effect':'require_peer_review'}]}
        with self.assertRaisesRegex(OrgError,'another member'):self.bench.call(self.org['id'],'a','release',args)
        self.assertIsNone(self.store.get(self.org['id'])['benchmarks'][self.run['id']]['release'])
        attempt=next(e for e in self.store.events(self.org['id']) if e['kind']=='benchmark.release_attempt')
        self.assertFalse(attempt['body']['allowed'])

    def test_upstream_actor_mapping_and_native_gate(self):
        with self.store.transaction(self.org['id'],'human','fixture',{}) as (org,db):
            org['organizationbench']={'url':'http://127.0.0.1:1','session_id':'fixture','actors':{'a':['agent-1'],'b':['agent-2'],'c':['agent-3']}}
            org['protocols']['p']={'id':'p','title':'deploy protection','status':'active','rules':[{'tools':['bench_deploy'],'effect':'deny'}]}
        args={'bench_actor':'agent-2','tool':'observe','arguments':{},'request_id':'one'}
        with self.assertRaises(OrgError):self.bench.upstream(self.org['id'],'a','invoke',args)
        with patch.object(Benchmarks,'request') as request:
            with self.assertRaisesRegex(OrgError,'deploy protection'):
                self.bench.upstream(self.org['id'],'a','invoke',{'tool':'deploy','arguments':{},'request_id':'two'})
            request.assert_not_called()


if __name__=='__main__':unittest.main()
