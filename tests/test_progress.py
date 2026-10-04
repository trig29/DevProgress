"""Tests of progress data/website generation only; no game code is executed."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from progress import calculate, make_snapshot, compare, task_score, group_status, weighted
from build_site import build, read, checked
from schema_check import validate_schema
from validate_todo import validate


def fixture():
    return read(ROOT/'todo.json')


def all_completed():
    data = fixture()
    data['evidence'].append({'id':'E-TEST-USER','source':'game_main','paths':[],'kind':'user_verification','summary':'Synthetic user verification fixture, never exported to the real site.'})
    for item in data['items']:
        if item['kind']=='task':
            item.update(status='done',assessment='assessed',implementation_location='main')
            item['evidence_ids'].append('E-TEST-USER')
    for score in data['manual_scores'].values():
        score['value'] = 100
    return data


class ProgressTests(unittest.TestCase):
    def test_fractional_weights_have_stable_precision(self):
        tasks=[{'weight':w,'status':s,'implementation_location':'main'} for w,s in [(0.1,'done'),(0.2,'in_progress'),(0.3,'not_started')]]
        self.assertEqual(weighted(tasks,fixture()['rules']),30.0)

    def test_real_baseline(self):
        result = calculate(fixture())
        self.assertAlmostEqual(result['overall'],34.747231715652774)
        dims = {d['id']:d for d in result['dimensions']}
        self.assertAlmostEqual(dims['art']['score'],17.87012987012987)
        self.assertIsNone(dims['art']['manual_score'])
        self.assertEqual(dims['art']['ui_score'],0)
        self.assertEqual(dims['polish']['score'], 10)
        self.assertEqual(dims['polish']['contribution'], 3)

    def test_complete_is_100_and_zero_is_real_zero(self):
        data = all_completed()
        self.assertEqual(validate(data), [])
        self.assertEqual(calculate(data)['overall'], 100)
        for item in data['items']:
            if item['kind']=='task':
                item['status']='not_started'
        for score in data['manual_scores'].values():
            score['value']=0
        self.assertEqual(calculate(data)['overall'], 0)

    def test_unknown_does_not_disappear_from_denominator(self):
        data = all_completed()
        task = next(i for i in data['items'] if i['kind']=='task' and i['dimension']=='story')
        task['status']=None
        self.assertIsNone(calculate(data)['overall'])
        self.assertIn(task['id'], calculate(data)['dimensions'][0]['unknown_task_ids'])

    def test_unknown_and_unstarted_group_does_not_claim_work_started(self):
        self.assertEqual(group_status([{'status':None},{'status':'not_started'}]),'pending_confirmation')

    def test_feature_branch_scores_status_without_claiming_integration(self):
        data = all_completed()
        task = next(i for i in data['items'] if i['id']=='system.minigame_play.implementation')
        task['implementation_location']='feature_branch'
        task['status']='in_progress'
        self.assertEqual(task_score(task,data['rules']),40)
        self.assertEqual(task['implementation_location'],'feature_branch')
        self.assertIsNotNone(calculate(data)['overall'])

    def test_draft_rules_block_scores_but_preserve_manual_values(self):
        data = all_completed(); data['rules']['approval']='draft'
        result = calculate(data)
        self.assertTrue(all(d['score'] is None for d in result['dimensions']))
        self.assertEqual(result['dimensions'][3]['manual_score'],100)

    def test_missing_manual_is_not_zero(self):
        data = all_completed(); data['manual_scores']['polish.manual']['value']=None
        self.assertIsNone(calculate(data)['overall'])
        self.assertIsNone(calculate(data)['dimensions'][3]['score'])

    def test_weighted_not_counted_and_ui_is_separate(self):
        data = all_completed()
        task = next(i for i in data['items'] if i['kind']=='task' and i['dimension']=='art')
        task['status']='not_started'
        total = sum(i['weight'] for i in data['items'] if i['kind']=='task' and i['dimension']=='art' and i['parent_id'] not in data['rules']['ui_group_ids'])
        expected=(100-100*task['weight']/total)*.8+100*.2
        self.assertAlmostEqual(calculate(data)['dimensions'][1]['score'],expected)

    def test_ui_tasks_use_only_the_ui_share_and_unknown_stays_unknown(self):
        data=all_completed()
        ui=[t for t in data['items'] if t['kind']=='task' and t['parent_id'] in data['rules']['ui_group_ids']]
        for t in ui:t['status']='not_started'
        art=calculate(data)['dimensions'][1]
        self.assertEqual(art['ui_score'],0)
        self.assertEqual(art['score'],80)
        ui[0]['status']=None
        self.assertIsNone(calculate(data)['dimensions'][1]['ui_score'])
        self.assertIsNone(calculate(data)['overall'])

    def test_ui_selection_rejects_duplicates_missing_and_non_art_groups(self):
        data=fixture();valid=data['rules']['ui_group_ids'][0]
        story=next(t['id'] for t in data['items'] if t['kind']=='group' and t['dimension']=='story')
        for ids in ([],[valid,valid],['missing'],[story]):
            data['rules']['ui_group_ids']=ids
            self.assertTrue(validate(data))
        data['rules']['ui_group_ids']=[t['id'] for t in data['items'] if t['kind']=='group' and t['dimension']=='art']
        self.assertTrue(validate(data))

    def test_schema_rejects_extra_fields_bool_scores_nan_and_bad_datetime(self):
        schema = read(ROOT/'todo.schema.json')
        for mutate in [lambda d:d.update(extra=True),lambda d:d['manual_scores']['polish.manual'].update(value=True),lambda d:d['manual_scores']['polish.manual'].update(value=float('nan')),lambda d:d['evaluation'].update(evaluated_at='2026-10-04')]:
            data=fixture();mutate(data);self.assertTrue(validate_schema(data,schema))

    def test_references_budget_and_done_proof(self):
        data=fixture();leaf=next(i for i in data['items'] if i['kind']=='task')
        leaf['weight']+=1;leaf['evidence_ids']=['missing'];leaf.update(status='done',assessment='assessed')
        errors=' '.join(validate(data))
        self.assertIn('budget',errors);self.assertIn('evidence reference',errors);self.assertIn('verification',errors)

    def test_scope_rule_changes_and_regression_deltas(self):
        config=read(ROOT/'site.config.json');data=all_completed()
        previous=make_snapshot(data,config)
        data['manual_scores']['polish.manual']['value']=0
        new=make_snapshot(data,config);compare(new,previous)
        self.assertAlmostEqual(new['update']['delta'],-30)
        data['snapshot']['scope_version']='demo-v2'
        newer=make_snapshot(data,config);compare(newer,new)
        self.assertFalse(newer['update']['comparable']);self.assertIsNone(newer['update']['delta'])
        self.assertTrue(any(r['type']=='demo_expansion' for r in newer['update']['change_reasons']))
        data['snapshot']['rules_version']='confirmed-v2'
        changed=make_snapshot(data,config);compare(changed,newer)
        self.assertTrue(any(r['type']=='rule_change' for r in changed['update']['change_reasons']))

    def test_future_tasks_do_not_score(self):
        data=all_completed()
        for i in data['items']:
            if i['id'].startswith('story.opening'):
                i.update(scope='future',status=None)
        self.assertEqual(calculate(data)['overall'],100)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=Path(self.temp.name)/'project';self.project.mkdir()
        import shutil
        for name in ['web','schemas']:
            shutil.copytree(ROOT/name,self.project/name)
        for name in ['todo.json','todo.schema.json','site.config.json']:
            shutil.copy2(ROOT/name,self.project/name)

    def tearDown(self):
        self.temp.cleanup()

    def test_idempotent_and_no_time_only_history(self):
        first,new=build(self.project,now='2026-10-04T01:00:00-04:00');self.assertTrue(new)
        second,new=build(self.project,now='2026-10-04T02:00:00-04:00');self.assertFalse(new)
        self.assertEqual(first['snapshot_id'],second['snapshot_id'])
        data=read(self.project/'todo.json');data['evaluation']['evaluated_at']='2026-10-04T02:00:00-04:00';data['snapshot']['date']='2026-10-05'
        (self.project/'todo.json').write_text(json.dumps(data))
        third,new=build(self.project);self.assertFalse(new)
        self.assertEqual(len(read(self.project/'history'/'snapshots.json')['snapshots']),1)
        self.assertEqual(third['evaluated_at'],data['evaluation']['evaluated_at'])
        import hashlib
        from progress import canonical
        self.assertEqual(third['todo_sha256'],hashlib.sha256(canonical(read(self.project/'site'/'data'/'todo.json'))).hexdigest())

    def test_manual_change_preserves_old_history_and_local_publication(self):
        old,_=build(self.project)
        data=read(self.project/'todo.json');data['manual_scores']['polish.manual']['value']=20
        (self.project/'todo.json').write_text(json.dumps(data))
        new,changed=build(self.project);self.assertTrue(changed)
        history=read(self.project/'history'/'snapshots.json')['snapshots']
        self.assertEqual(history[0]['dimensions'][3]['score'],10)
        self.assertEqual(history[1]['dimensions'][3]['score'],20)
        self.assertIsNone(new['published_at'])
        self.assertAlmostEqual(new['update']['delta'],3)
        self.assertEqual(history[0]['snapshot_id'],old['snapshot_id'])

    def test_output_allowlist_and_full_download(self):
        (self.project/'剧情正文.md').write_text('Not for publication')
        (self.project/'config.local.json').write_text('{"game_repository":"/Users/private"}')
        build(self.project)
        output=self.project/'site'
        self.assertEqual(read(output/'data'/'todo.json'),read(self.project/'todo.json'))
        self.assertFalse((output/'剧情正文.md').exists());self.assertFalse((output/'config.local.json').exists())
        self.assertEqual(set(p.name for p in output.iterdir()),{'index.html','dimensions.html','updates.html','todos.html','history.html','method.html','assets','data','.nojekyll','.devprogress-output'})

    def test_invalid_data_leaves_previous_export_and_history_intact(self):
        build(self.project);original=(self.project/'history'/'snapshots.json').read_bytes();output=(self.project/'site'/'data'/'current.json').read_bytes()
        data=read(self.project/'todo.json');data['items'][1]['parent_id']='missing'
        (self.project/'todo.json').write_text(json.dumps(data))
        with self.assertRaises(ValueError):build(self.project)
        self.assertEqual((self.project/'history'/'snapshots.json').read_bytes(),original)
        self.assertEqual((self.project/'site'/'data'/'current.json').read_bytes(),output)

    def test_dirty_source_and_unowned_output_rejected(self):
        data=read(self.project/'todo.json');data['sources'][1]['dirty']=True
        (self.project/'todo.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'committed baseline'):build(self.project)
        (self.project/'todo.json').write_text(json.dumps(fixture()))
        unowned=self.project/'unowned';unowned.mkdir()
        with self.assertRaisesRegex(ValueError,'Refusing'):build(self.project,unowned)


if __name__=='__main__':unittest.main()
