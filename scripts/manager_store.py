"""Local-only draft validation, transactions and recovery. Never invokes Git or Godot."""
import copy
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from build_site import build, read, checked
from progress import canonical, calculate
from site_content import load_content, validate_content
from validate_todo import validate

def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.json-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)

class ProjectLock:
    """Serialize threads and separate local-manager processes for one project."""
    def __init__(self,path):
        self.thread=threading.RLock();self.file=open(path,'a');self.depth=0
    def __del__(self):
        if hasattr(self,'file'):self.file.close()
    def __enter__(self):
        self.thread.acquire()
        if self.depth==0:fcntl.flock(self.file.fileno(),fcntl.LOCK_EX)
        self.depth+=1
        return self
    def __exit__(self,*args):
        self.depth-=1
        if self.depth==0:fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
        self.thread.release()

def preserve_number_types(value, template):
    # JSON.stringify collapses 1.0 to 1. Preserve the existing numeric encoding
    # so a browser round trip cannot manufacture a new historical snapshot.
    if isinstance(value, dict) and isinstance(template, dict):
        return {k:preserve_number_types(v,template.get(k)) for k,v in value.items()}
    if isinstance(value,list) and isinstance(template,list):
        indexed={x['id']:x for x in template if isinstance(x,dict) and 'id' in x}
        return [preserve_number_types(v,indexed.get(v.get('id')) if isinstance(v,dict) and 'id' in v else (template[i] if i<len(template) else None)) for i,v in enumerate(value)]
    if isinstance(value,(int,float)) and not isinstance(value,bool) and isinstance(template,float):
        return float(value)
    return value

class Conflict(ValueError):
    pass

def migrate_legacy_bundle(bundle):
    """Restore old local drafts/backups without reintroducing removed task fields."""
    todo=bundle['todo']
    if todo.get('schema_version') in {'1.0.0','1.1.0'}:
        for item in todo['items']:item.pop('dependencies',None)
        todo['schema_version']='1.2.0'
    for entry in bundle.get('trash',[]):
        for item in entry['items']:item.pop('dependencies',None)
    return bundle

class Store:
    def __init__(self, root):
        self.root=Path(root).resolve()
        self.local=self.root/'.local-manager'
        self.local.mkdir(exist_ok=True)
        self.lock=ProjectLock(self.local/'manager.lock')
        self.preview_path=None
        self.files=('todo.json','site.config.json','site.content.json')

    def now(self):
        return datetime.now(ZoneInfo(read(self.root/'site.config.json')['timezone'])).isoformat(timespec='seconds')

    def revision(self):
        paths=[self.root/f for f in self.files]+[self.root/'history/snapshots.json',self.root/'todo.schema.json']
        paths+=sorted((self.root/'schemas').glob('*.json'))
        paths+=sorted((self.root/'web').rglob('*'))
        digest=hashlib.sha256()
        for p in paths:
            if p.is_file():
                digest.update(str(p.relative_to(self.root)).encode());digest.update(p.read_bytes())
        return digest.hexdigest()

    def bundle(self):
        return {'todo':read(self.root/'todo.json'),'config':read(self.root/'site.config.json'),'content':load_content(self.root),
                'trash':self.trash(), 'change':{'type':'status_update','reason':''}, 'verifications':{},'manual_notes':{}}

    def trash(self):
        return read(self.local/'trash.json') if (self.local/'trash.json').exists() else []

    def records(self):
        return read(self.local/'records.json') if (self.local/'records.json').exists() else []

    def state(self):
        with self.lock:
            draft=read(self.local/'draft.json') if (self.local/'draft.json').exists() else None
            return {'base_revision':self.revision(),'official':self.bundle(),'draft':draft,'records':self.records(),
                    'calculation':calculate(read(self.root/'todo.json'))}

    def guard(self, request, draft=True):
        if request.get('base_revision')!=self.revision():
            raise Conflict('正式文件已被修改。请导出草稿后重新载入，禁止覆盖。')
        saved=read(self.local/'draft.json') if (self.local/'draft.json').exists() else None
        expected=saved['draft_revision'] if saved else 0
        if draft and request.get('draft_revision',0)!=expected:
            raise Conflict('草稿已由其他窗口修改，请重新载入。')
        return expected

    def save(self, request):
        with self.lock:
            rev=self.guard(request)
            bundle=request['bundle']
            if not isinstance(bundle,dict) or set(bundle)!=set(self.bundle()):
                raise ValueError('草稿结构无效')
            # Drafts may be incomplete; strict validation happens before preview/apply.
            canonical(bundle)
            value={'base_revision':request['base_revision'],'draft_revision':rev+1,'bundle':bundle,'saved_at':self.now()}
            write(self.local/'draft.json',value)
            return value

    def discard(self, request):
        with self.lock:
            self.guard(request)
            (self.local/'draft.json').unlink(missing_ok=True)
            return self.state()

    def restore(self, request):
        with self.lock:
            self.guard(request)
            record=next((r for r in self.records() if r['id']==request.get('id')),None)
            if not record:raise ValueError('应用记录不存在')
            backup=self.local/'backups'/record['id']
            bundle=self.bundle()
            bundle.update(todo=read(backup/'todo.json'),config=read(backup/'site.config.json'),content=load_content(backup))
            bundle['trash']=read(backup/'trash.json')
            migrate_legacy_bundle(bundle)
            bundle['change']={'type':'demo_expansion','reason':'从应用记录恢复旧数据，保留现有历史；范围或规则变化按恢复后的数据记录'}
            bundle['manual_notes']={i:'用户从应用记录恢复旧的手动评分' for i in bundle['todo']['manual_scores']}
            source=bundle['todo']['project']['target_source']
            for item in bundle['todo']['items']:
                if item['kind']=='task' and item['status']=='done':
                    evidence=next((e for e in bundle['todo']['evidence'] if e['id'] in item['evidence_ids'] and e['kind']=='user_verification'),None)
                    if evidence:
                        bundle['verifications'][item['id']]={'note':'恢复有效人工验收：'+evidence['summary'],'location':item['implementation_location'],'source':evidence['source']}
            return self.save({**request,'bundle':bundle})

    def normalized(self, bundle):
        old=self.bundle();new=migrate_legacy_bundle(copy.deepcopy(bundle));todo=preserve_number_types(new['todo'],old['todo']);new['todo']=todo;base=old['todo'];stamp=(read(self.local/'draft.json')['saved_at'] if (self.local/'draft.json').exists() else self.now())
        if not isinstance(new.get('change'),dict):raise ValueError('变更类型和原因无效')
        kind=new['change'].get('type');reason=new['change'].get('reason','').strip()
        if kind not in {'status_update','refinement','demo_expansion','future','rule_change','manual_score_update'}:raise ValueError('变更类型无效')
        for key in ('sources','project','dimensions','schema_version','$schema'):
            if todo.get(key)!=base.get(key):raise ValueError(f'{key} 由数据源维护，不可通过管理接口改写')
        for key in base['snapshot']:
            if key not in ('date','scope_version','rules_version') and todo['snapshot'].get(key)!=base['snapshot'][key]:
                raise ValueError('基线元数据不可通过管理接口改写')
        todo['snapshot']=copy.deepcopy(base['snapshot'])
        if new['config'].keys()!=old['config'].keys() or any(new['config'][k]!=old['config'][k] for k in old['config'] if k not in ('title','phase_label')):
            raise ValueError('只允许修改网站名称和阶段标签，不允许修改发布配置或本机设置')
        if any(not isinstance(new['config'][k],str) or not new['config'][k].strip() for k in ('title','phase_label')):raise ValueError('网站名称与阶段不能为空')
        validate_content(new['content'])
        old_items={t['id']:t for t in base['items']};items={t['id']:t for t in todo['items']}
        if set(todo['manual_scores'])!=set(base['manual_scores']):raise ValueError('UI 与打磨评分项目不可新增或删除')
        if any(items.get(i,{}).get('kind')!='manual' for i,t in old_items.items() if t['kind']=='manual'):raise ValueError('手动评分项目不可删除或转为普通任务')
        removed=set(old_items)-set(items)
        archived={t['id'] for entry in new['trash'] for t in entry['items']}
        if not removed<=archived:raise ValueError('删除任务必须进入回收站')
        if set(items)&archived:raise ValueError('恢复后必须移出回收站，不能重复使用 ID')
        for i,item in items.items():
            if i in old_items and item['kind']!=old_items[i]['kind']:raise ValueError('已有任务类型不可更改')
            if item['kind']=='task':
                item['assessment']='pending_confirmation' if item['status'] is None else 'assessed'
                previous=old_items.get(i,{})
                requires=item['status']=='done' and (previous.get('status')!='done' or previous.get('implementation_location')!=item['implementation_location'] or previous.get('completion_criteria')!=item['completion_criteria'])
                if requires:
                    v=new['verifications'].get(i,{})
                    if not v.get('note','').strip() or v.get('location')!=item['implementation_location'] or not v.get('source'):
                        raise ValueError(f'{i}: 标为已完成需要验收说明、适用分支及来源基线')
                    source=next((s for s in todo['sources'] if s['id']==v['source'] and s['kind']=='git'),None)
                    target=todo['project']['target_source']
                    if not source or (v['location']=='main' and source['id']!=target) or (v['location']=='feature_branch' and source['id']==target) or v['location'] not in ('main','feature_branch'):
                        raise ValueError(f'{i}: 验收分支与来源基线不匹配')
                    eid='E-USER-'+hashlib.sha256(canonical([i,stamp,v])).hexdigest()[:16]
                    todo['evidence'].append({'id':eid,'source':v['source'],'paths':[],'kind':'user_verification','summary':f'{stamp} 用户验收（{v["location"]}）：{v["note"].strip()}'})
                    item['evidence_ids'].append(eid)
        for i,score in todo['manual_scores'].items():
            prev=base['manual_scores'][i]
            if score['value']!=prev['value']:
                note=new['manual_notes'].get(i,'').strip()
                if not note:raise ValueError(f'{i}: 手动评分变更需要来源说明')
                score.update(updated_by='user',updated_at=stamp,evidence=prev['evidence']+[f'{stamp} 本地管理工具：{note}'])
            else:
                todo['manual_scores'][i]=copy.deepcopy(prev)
        def scope_signature(data):
            return sorted((i['id'],i['parent_id'],i['dimension'],i['scope']) for i in data['items'] if i['kind']!='manual' and i['scope']=='demo')
        structure_changed=scope_signature(todo)!=scope_signature(base)
        budget_changed=todo['group_budgets']!=base['group_budgets']
        demo_budget_changed=any(todo['group_budgets'].get(i)!=base['group_budgets'].get(i) for i in set(todo['group_budgets'])|set(base['group_budgets']) if (items.get(i) or old_items.get(i))['scope']=='demo')
        weights_changed=any(t['kind']=='task' and i in old_items and t['weight']!=old_items[i]['weight'] for i,t in items.items())
        rules_changed=todo['rules']!=base['rules']
        if (structure_changed or budget_changed or weights_changed or rules_changed) and not reason:raise ValueError('任务结构、权重、范围或规则变化必须填写变更原因')
        if structure_changed or budget_changed:
            if kind not in ('refinement','demo_expansion','future'):raise ValueError('结构或预算变化请选择“目标细化”“Demo范围变化”或“后续计划”')
            if kind=='refinement' and (budget_changed or any(t['scope']!=old_items[i]['scope'] or t['dimension']!=old_items[i]['dimension'] for i,t in items.items() if i in old_items)):
                raise ValueError('目标细化必须保持原大项预算、维度和范围；其他情况请选择 Demo 范围变化')
            if kind!='refinement' and (structure_changed or demo_budget_changed):todo['snapshot']['scope_version']=base['snapshot']['scope_version']+'-'+hashlib.sha256(canonical([todo['items'],todo['group_budgets']])).hexdigest()[:8]
        if rules_changed:
            factors=todo['rules']['status_factors']
            if factors['not_started']!=0 or factors['done']!=1 or not 0<=factors['in_progress']<=factors['implemented_unverified']<=1:
                raise ValueError('状态档位必须递增，未开始为0%，已完成为100%')
            if kind not in ('rule_change','demo_expansion','refinement','future'):raise ValueError('评分规则变化请选择规则变更类型')
            todo['snapshot']['rules_version']=base['snapshot']['rules_version']+'-'+hashlib.sha256(canonical(todo['rules'])).hexdigest()[:8]
            r=todo['rules'];r['calculation']=f'剧情/系统按叶项相对权重计算；美术 UI 占 {r["art_ui_share"]*100:g}%；整体维度比例 '+ ' / '.join(f'{k}={v*100:g}%' for k,v in r['dimension_shares'].items())+'。未知值保持 null。'
        if todo['change_log']!=base['change_log']:todo['change_log']=copy.deepcopy(base['change_log'])
        # Evaluation timestamps and versions are assigned by the application, never accepted as user input.
        todo['evaluation']['evaluated_at']=base['evaluation']['evaluated_at']
        if canonical(todo)!=canonical(base):
            todo['evaluation']['evaluated_at']=stamp;todo['snapshot']['date']=stamp[:10]
            summary=reason or '本地管理工具手动更新任务、评分或评估内容'
            todo['change_log'].append({'date':stamp[:10],'type':kind,'scope_version':todo['snapshot']['scope_version'],'rules_version':todo['snapshot']['rules_version'],
                                      'game_commit':next(s['commit'] for s in todo['sources'] if s['id']==todo['project']['target_source']),'summary':summary})
            if reason:
                etype={'status_update':'verification'}.get(kind,kind)
                todo['evaluation']['change_reasons'].append({'type':etype,'text':reason})
        old_evidence={e['id']:e for e in base['evidence']}
        for e in todo['evidence']:
            if e['kind']=='user_verification' and e['summary'] and e!=old_evidence.get(e['id']) and not e['summary'].startswith(stamp):
                e['summary']=stamp+' 用户验收：'+e['summary']
        checked(todo,read(self.root/'todo.schema.json'))
        errors=validate(todo)
        if errors:raise ValueError('\n'.join(errors))
        # Relative public evidence paths only; build also checks this.
        for e in todo['evidence']:
            for path in e['paths']:
                if Path(path).is_absolute() or '..' in Path(path).parts or path.startswith(('file:','C:\\')):raise ValueError('证据路径必须是仓库相对路径')
        return new

    def stage(self, bundle):
        path=Path(tempfile.mkdtemp(prefix='stage-',dir=self.local))
        try:
            for name in ('todo.schema.json',):shutil.copy2(self.root/name,path/name)
            for name in ('web','schemas','history'):shutil.copytree(self.root/name,path/name)
            for name,key in zip(self.files,('todo','config','content')):write(path/name,bundle[key])
            snapshot,changed=build(path)
            return path,snapshot,changed
        except Exception:
            shutil.rmtree(path,ignore_errors=True);raise

    def diff(self, a,b, path=''):
        if a==b:return []
        if isinstance(a,dict) and isinstance(b,dict):
            out=[]
            for k in sorted(set(a)|set(b)):
                out+=self.diff(a.get(k),b.get(k),f'{path}.{k}' if path else k)
            return out
        if isinstance(a,list) and isinstance(b,list) and all(isinstance(x,dict) and 'id' in x for x in a+b):
            return self.diff({x['id']:x for x in a},{x['id']:x for x in b},path)
        return [{'field':path,'before':a,'after':b}]

    def preview(self, request):
        with self.lock:
            self.guard(request);bundle=self.normalized(request['bundle'])
            path,snapshot,changed=self.stage(bundle)
            if self.preview_path:shutil.rmtree(self.preview_path,ignore_errors=True)
            self.preview_path=path
            return {'valid':True,'before':calculate(self.bundle()['todo']),'after':calculate(bundle['todo']),
                    'diff':self.diff(self.bundle()['todo'],bundle['todo'],'todo')+self.diff(self.bundle()['config'],bundle['config'],'config')+self.diff(load_content(self.root),bundle['content'],'content'),
                    'new_snapshot':changed,'snapshot_id':snapshot['snapshot_id'],'preview_url':'/draft-preview/','scope_warning':bundle['todo']['snapshot']['scope_version']!=self.bundle()['todo']['snapshot']['scope_version']}

    def apply(self, request):
        with self.lock:
            self.guard(request);bundle=self.normalized(request['bundle'])
            path,snapshot,changed=self.stage(bundle)
            try:self.guard(request)
            except Exception:
                shutil.rmtree(path,ignore_errors=True);raise
            id=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
            backup=self.local/'backups'/id;backup.mkdir(parents=True)
            for name in self.files:
                if (self.root/name).exists():shutil.copy2(self.root/name,backup/name)
            write(backup/'trash.json',self.trash())
            shutil.copy2(self.root/'history/snapshots.json',backup/'history.json')
            old_site=self.root/'site';moved=False;installed=False
            records=self.records()
            try:
                for name in self.files:os.replace(path/name,self.root/name)
                os.replace(path/'history/snapshots.json',self.root/'history/snapshots.json')
                if old_site.exists():os.replace(old_site,path/'old-site');moved=True
                os.replace(path/'site',old_site);installed=True
                write(self.local/'trash.json',bundle['trash'])
                record={'id':id,'time':self.now(),'summary':bundle['change']['reason'] or '手动编辑本地内容','snapshot_id':snapshot['snapshot_id'],'new_snapshot':changed}
                write(self.local/'records.json',records+[record])
                (self.local/'draft.json').unlink(missing_ok=True)
            except Exception:
                for name in self.files:
                    if (backup/name).exists():shutil.copy2(backup/name,self.root/name)
                    else:(self.root/name).unlink(missing_ok=True)
                shutil.copy2(backup/'history.json',self.root/'history/snapshots.json')
                if installed:shutil.rmtree(old_site)
                if moved:os.replace(path/'old-site',old_site)
                write(self.local/'trash.json',read(backup/'trash.json'));write(self.local/'records.json',records)
                raise
            finally:shutil.rmtree(path,ignore_errors=True)
            return {'record':record,'state':self.state(),'preview_url':'/preview/'}
