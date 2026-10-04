"""Isolated manager checks; no real progress data or game files are changed."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from manager_store import Store, Conflict
from build_site import build, read, write

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for f in ('todo.json','todo.schema.json','site.config.json','site.content.json'):shutil.copy2(ROOT/f,self.root/f)
        for d in ('web','schemas','history'):shutil.copytree(ROOT/d,self.root/d)
        build(self.root);self.store=Store(self.root)
        self.request={'base_revision':self.store.revision(),'draft_revision':0,'bundle':self.store.bundle()}
    def tearDown(self):self.tmp.cleanup()
    def save(self):
        saved=self.store.save(self.request);self.request['draft_revision']=saved['draft_revision'];return saved
    def task(self):return next(t for t in self.request['bundle']['todo']['items'] if t['kind']=='task')
    def test_draft_persists_and_conflicts(self):
        before=(self.root/'todo.json').read_bytes();self.task()['title']='草稿名称';self.save()
        self.assertEqual(before,(self.root/'todo.json').read_bytes());self.assertEqual(Store(self.root).state()['draft']['bundle']['todo']['items'],self.request['bundle']['todo']['items'])
        with self.assertRaises(Conflict):self.store.save({**self.request,'draft_revision':0})
        todo=read(self.root/'todo.json');todo['evaluation']['highlights'].append('外部修改');write(self.root/'todo.json',todo)
        with self.assertRaises(Conflict):self.store.apply(self.request)
    def test_copy_preview_and_apply_no_history(self):
        history=read(self.root/'history/snapshots.json');self.request['bundle']['content']['pages']['todos']['intro']='新的说明';self.save()
        result=self.store.preview(self.request);self.assertFalse(result['new_snapshot']);self.assertEqual(history,read(self.root/'history/snapshots.json'))
        self.store.apply(self.request);self.assertEqual(history,read(self.root/'history/snapshots.json'));self.assertEqual(read(self.root/'site/data/content.json')['pages']['todos']['intro'],'新的说明')
        self.assertFalse((self.root/'site/manager').exists());self.assertFalse((self.root/'site/.local-manager').exists())
    def test_manual_unknown_zero_and_restore_history(self):
        initial_count=len(read(self.root/'history/snapshots.json')['snapshots'])
        score=self.request['bundle']['todo']['manual_scores']['art.ui'];score['value']=0;self.request['bundle']['manual_notes']['art.ui']='用户实际评分为零';self.save()
        first=self.store.apply(self.request);self.assertTrue(first['record']['new_snapshot']);self.assertEqual(read(self.root/'todo.json')['manual_scores']['art.ui']['value'],0)
        state=self.store.state();req={'base_revision':state['base_revision'],'draft_revision':0,'id':first['record']['id']}
        draft=self.store.restore(req);req.update(bundle=draft['bundle'],draft_revision=draft['draft_revision']);self.store.apply(req)
        self.assertEqual(read(self.root/'todo.json')['manual_scores']['art.ui']['value'],50)
        self.assertEqual(len(read(self.root/'history/snapshots.json')['snapshots']),initial_count+2)
    def test_missing_manual_source_and_done_evidence(self):
        self.request['bundle']['todo']['manual_scores']['art.ui']['value']=None
        with self.assertRaisesRegex(ValueError,'来源说明'):self.store.normalized(self.request['bundle'])
        self.request['bundle']=self.store.bundle();t=self.task();t.update(status='done',implementation_location='main')
        with self.assertRaisesRegex(ValueError,'验收说明'):self.store.normalized(self.request['bundle'])
        self.request['bundle']['verifications'][t['id']]={'note':'用户确认该设计完成','location':'main','source':'game_main'}
        self.save();a=self.store.preview(self.request);b=self.store.apply(self.request);self.assertEqual(a['snapshot_id'],b['record']['snapshot_id'])
    def test_unknown_score_and_moving_one_child(self):
        b=self.request['bundle'];b['todo']['manual_scores']['art.ui']['value']=None;b['manual_notes']['art.ui']='暂未确认新 UI 评分'
        result=self.store.normalized(b);self.assertIsNone(result['todo']['manual_scores']['art.ui']['value'])
        b=self.store.bundle();tasks=[t for t in b['todo']['items'] if t['kind']=='task'];moving=tasks[0];parent=next(g for g in b['todo']['items'] if g['kind']=='group' and g['id']!=moving['parent_id'] and g['dimension']==moving['dimension'])
        old_parent=moving['parent_id'];weight=moving['weight'];moving['parent_id']=parent['id'];b['todo']['group_budgets'][old_parent]-=weight;b['todo']['group_budgets'][parent['id']]+=weight
        # Empty source group must also be removed explicitly; do not implicitly move siblings.
        old_group=next(g for g in b['todo']['items'] if g['id']==old_parent)
        b['trash']=[{'id':'trash.move','items':[old_group],'budgets':{old_parent:b['todo']['group_budgets'][old_parent]}}]
        b['todo']['items']=[g for g in b['todo']['items'] if g['id']!=old_parent];del b['todo']['group_budgets'][old_parent]
        for section in ('candidate_notes','pending_decisions'):
            for r in b['todo'][section]:r['related_ids']=[i for i in r['related_ids'] if i!=old_parent]
        b['change']={'type':'demo_expansion','reason':'移动一个子项并显式移除空组'}
        result=self.store.normalized(b);self.assertEqual(next(t for t in result['todo']['items'] if t['id']==moving['id'])['parent_id'],parent['id'])

    def test_branch_done_stays_unknown(self):
        t=self.task();t.update(status='done',implementation_location='feature_branch');self.request['bundle']['verifications'][t['id']]={'note':'功能分支人工验收通过','location':'feature_branch','source':'game_minigame'}
        value=self.store.normalized(self.request['bundle']);from progress import task_score
        task=next(x for x in value['todo']['items'] if x['id']==t['id']);self.assertIsNone(task_score(task,value['todo']['rules']))
    def test_legacy_draft_removes_dependencies(self):
        b=self.request['bundle'];b['todo']['schema_version']='1.1.0'
        for t in b['todo']['items']:t['dependencies']=['old-task']
        self.task()['title']='保留草稿修改'
        result=self.store.normalized(b)
        self.assertEqual(result['todo']['schema_version'],'1.2.0')
        self.assertFalse(any('dependencies' in t for t in result['todo']['items']))
        self.assertEqual(next(t for t in result['todo']['items'] if t['kind']=='task')['title'],'保留草稿修改')

    def test_bad_budget(self):
        self.task()['weight']+=1;self.request['bundle']['change']={'type':'refinement','reason':'调整子项'}
        with self.assertRaisesRegex(ValueError,'budget'):self.store.normalized(self.request['bundle'])
    def test_rule_versions_and_ranges(self):
        b=self.request['bundle'];b['todo']['rules']['art_ui_share']=.3;b['change']={'type':'rule_change','reason':'调整 UI 比例'};self.save()
        p=self.store.preview(self.request);a=self.store.apply(self.request);self.assertEqual(p['snapshot_id'],a['record']['snapshot_id']);self.assertNotEqual(read(self.root/'todo.json')['snapshot']['rules_version'],'confirmed-v1')
    def test_failed_apply_rolls_back(self):
        before={p:(self.root/p).read_bytes() for p in ('todo.json','site.config.json','history/snapshots.json','site/data/current.json')};self.task()['title']='修改标题';self.save()
        import manager_store
        original=manager_store.os.replace
        def fail(src,dst):
            if Path(src).name=='site':raise OSError('injected failure')
            return original(src,dst)
        with patch('manager_store.os.replace',side_effect=fail):
            with self.assertRaises(OSError):self.store.apply(self.request)
        for p,value in before.items():self.assertEqual((self.root/p).read_bytes(),value)
        self.assertTrue((self.store.local/'draft.json').exists())
    def test_duplicate_apply_no_new_snapshot(self):
        self.task()['title']='有效改名';self.save();self.store.apply(self.request);n=len(read(self.root/'history/snapshots.json')['snapshots'])
        s=self.store.state();req={'base_revision':s['base_revision'],'draft_revision':0,'bundle':s['official']};self.assertFalse(self.store.apply(req)['record']['new_snapshot']);self.assertEqual(len(read(self.root/'history/snapshots.json')['snapshots']),n)
    def test_deleted_related_reference_rejected(self):
        b=self.request['bundle'];todo=b['todo'];group=next(t for t in todo['items'] if t['kind']=='group');ids={group['id']}|{t['id'] for t in todo['items'] if t['parent_id']==group['id']};gone=[t for t in todo['items'] if t['id'] in ids]
        b['trash']=[{'id':'trash.test','items':gone,'budgets':{group['id']:todo['group_budgets'][group['id']]}}];todo['items']=[t for t in todo['items'] if t['id'] not in ids];del todo['group_budgets'][group['id']];b['change']={'type':'demo_expansion','reason':'移除范围内目标'}
        todo['pending_decisions'][0]['related_ids']=[gone[-1]['id']]
        with self.assertRaisesRegex(ValueError,'related ID'):self.store.normalized(b)
        for k in ('candidate_notes','pending_decisions'):
            for r in todo[k]:r['related_ids']=[i for i in r['related_ids'] if i not in ids]
        value=self.store.normalized(b);self.assertNotEqual(value['todo']['snapshot']['scope_version'],'demo-v1')
    def test_refinement_preserves_budget(self):
        b=self.request['bundle'];t=self.task();extra=copy.deepcopy(t);extra['id']='task.new-refinement';extra['title']='目标细分';t['weight']/=2;extra['weight']=t['weight'];b['todo']['items'].append(extra);b['change']={'type':'refinement','reason':'原目标细分，保留预算'}
        value=self.store.normalized(b);self.assertEqual(value['todo']['snapshot']['scope_version'],'demo-v1')
    def test_browser_numeric_roundtrip_is_not_progress(self):
        import re
        b=json.loads(re.sub(r'(?<=\d)\.0(?=[,}\]])','',json.dumps(self.request['bundle'])))
        self.assertEqual(self.store.normalized(b)['todo'],self.store.bundle()['todo'])
        self.request['bundle']=b;self.save();self.assertFalse(self.store.preview(self.request)['new_snapshot'])

    def test_config_and_plain_text(self):
        b=self.request['bundle'];b['config']['publication']['enabled']=not b['config']['publication']['enabled']
        with self.assertRaisesRegex(ValueError,'发布配置'):self.store.normalized(b)
        b=self.store.bundle();b['content']['pages']['todos']['intro']='<script>alert(1)</script>'
        self.assertEqual(self.store.normalized(b)['content']['pages']['todos']['intro'],'<script>alert(1)</script>')


class SessionTests(unittest.TestCase):
    def test_existing_service_matches_project_only(self):
        from manage import make_handler, existing_manager
        from http.server import ThreadingHTTPServer
        from types import SimpleNamespace
        import threading
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(SimpleNamespace(root=root),'secret',0))
            port=server.server_port
            server.RequestHandlerClass=make_handler(SimpleNamespace(root=root),'secret',port)
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                self.assertTrue(existing_manager(root,port))
                self.assertFalse(existing_manager(root/'other',port))
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_origin_session_and_host_guards(self):
        from manage import make_handler
        Handler=make_handler(None,'session-secret',4174)
        handler=object.__new__(Handler)
        errors=[];handler.error=lambda code,message:errors.append(code)
        handler.headers={'Host':'127.0.0.1:4174','Origin':'http://127.0.0.1:4174','X-Session-Token':'session-secret'}
        self.assertTrue(handler.auth(True))
        handler.headers['Origin']='https://example.com';self.assertFalse(handler.auth(True));self.assertEqual(errors[-1],403)
        handler.headers['Origin']='http://127.0.0.1:4174';handler.headers['X-Session-Token']='bad';self.assertFalse(handler.auth(True))
        handler.headers['X-Session-Token']='session-secret';handler.headers['Host']='example.com';self.assertFalse(handler.auth())

if __name__=='__main__':unittest.main()
