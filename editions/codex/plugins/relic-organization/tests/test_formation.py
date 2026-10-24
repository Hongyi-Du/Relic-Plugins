import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_org.bridge import BridgeUnavailable
from relic_org.service import Service
from relic_org.store import Store, OrgError


class Host:
    def __init__(self):
        self.calls = []
        self.sent = []
        self.fail_creation = False
        self.ready_response = None
        self.projects = []

    def inventory(self, include_archived=False):
        return [{'id':'caller','title':'Current chat','cwd':'current/workspace'}]

    def call(self, name, args):
        self.calls.append((name,args))
        if name == 'create_thread':
            if self.fail_creation:
                raise BridgeUnavailable('Timeout after native create request')
            n = sum(name == 'create_thread' for name,_ in self.calls)
            if self.ready_response is not None:
                return self.ready_response
            return {'threadId':f'new-{n}','hostId':'local','projectlessOutputDirectory':f'C:/own/workspace-{n}/outputs'}
        if name == 'list_projects':
            return {'projects':self.projects}
        raise AssertionError(name)

    def send(self, member, prompt):
        self.sent.append(member['thread_id'])
        return {'success':True}

    def close(self):pass


class FormationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'test.sqlite3')
        self.host = Host()
        self.service = Service(self.store,self.host,'caller')
        self.args = {'operation':'start','request_id':'create-1','data':{'name':'New organization','task':'Build a cooperative CLI','new_members':2,'execution_mode':'desktop'}}

    def tearDown(self):self.temp.cleanup()

    def test_create_enroll_workspace_and_retry_no_duplicates(self):
        result = self.service.call('org_organize',self.args)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['leader'],'caller')
        self.assertEqual(result['members'],['caller','new-1','new-2'])
        org = self.store.get(result['org_id'])
        self.assertEqual(org['members']['new-2']['workspace'],'C:\\own\\workspace-2' if sys.platform=='win32' else 'C:/own/workspace-2')
        self.assertIn('Build a cooperative CLI',org['documents']['human-task-brief']['body'])
        self.assertEqual(len(self.host.calls),2)
        self.assertTrue(all('Build a cooperative CLI' in args['prompt'] for name,args in self.host.calls if name=='create_thread'))
        repeated = self.service.call('org_organize',self.args)
        self.assertEqual(result,repeated)
        self.assertEqual(len(self.host.calls),2)
        self.assertEqual(self.service.call('org_organize',{'operation':'status','request_id':'create-1','data':{}}),result)

    def test_unknown_creation_keeps_receipt_without_retry(self):
        self.host.fail_creation = True
        one = self.service.call('org_organize',self.args)
        self.assertEqual(one['status'],'uncertain')
        self.service.call('org_organize',self.args)
        self.assertEqual(len(self.host.calls),1)
        self.assertEqual(self.store.list(),[])

    def test_changed_request_or_another_caller_cannot_reuse(self):
        self.service.call('org_organize',self.args)
        with self.assertRaises(OrgError):
            self.service.call('org_organize',{**self.args,'data':{**self.args['data'],'task':'Different task'}})
        with self.assertRaises(OrgError):
            self.service.call('org_organize',{'operation':'status','request_id':'create-1','data':{}},actor='someone-else')

    def test_busy_current_chat_rejected_before_any_new_chat(self):
        self.store.create('Busy',[{'thread_id':'caller'}],'caller')
        with self.assertRaises(OrgError):self.service.call('org_organize',self.args)
        self.assertEqual(self.host.calls,[])

    def test_window_can_create_all_members_without_existing_selection(self):
        result = self.service.call('org_organize',{**self.args,'data':{**self.args['data'],'include_current':False}})
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['leader'],'new-1')
        self.assertEqual(result['members'],['new-1','new-2'])

    def test_invalid_shape_is_rejected_before_mutation(self):
        for extra in [{'new_members':True},{'new_members':25},{'leader':'not-selected'},{'members':['caller','caller']},{'include_current':'yes'}]:
            with self.subTest(extra=extra),self.assertRaises(OrgError):
                self.service.call('org_organize',{**self.args,'data':{**self.args['data'],**extra}})
        self.assertEqual(self.host.calls,[])

    def test_malformed_ready_receipt_preserves_known_chat_without_retry(self):
        for index, response in enumerate([
            {'threadId':'known-no-workspace','hostId':'local'},
            {'threadId':'known-remote','hostId':'remote','projectlessOutputDirectory':'C:/remote/outputs'},
        ]):
            with self.subTest(response=response):
                self.host.ready_response = response
                args={**self.args,'request_id':f'bad-ready-{index}'}
                result=self.service.call('org_organize',args)
                self.assertEqual(result['status'],'uncertain')
                self.assertEqual(result['created_threads'][0]['thread_id'],response['threadId'])
                self.assertEqual(result['created_threads'][0]['creation'],response)
                calls=len(self.host.calls)
                self.assertEqual(self.service.call('org_organize',args),result)
                self.assertEqual(len(self.host.calls),calls)
                self.assertIsNone(result['org_id'])
                self.assertEqual(self.store.list(),[])

    def test_local_project_workspace_without_projectless_metadata(self):
        self.host.projects=[{'projectId':'project-1','projectKind':'local','hostId':'local','path':'C:/project'}]
        self.host.ready_response={'threadId':'project-member','hostId':'local'}
        args={**self.args,'data':{**self.args['data'],'new_members':1,'project_id':'project-1'}}
        result=self.service.call('org_organize',args)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['created_threads'][0]['workspace'],'C:/project')
        self.assertEqual(self.store.get(result['org_id'])['members']['project-member']['workspace'],'C:/project')

if __name__=='__main__':unittest.main()
