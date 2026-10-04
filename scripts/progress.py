"""Deterministic progress calculation. No game execution or repository mutation."""
import hashlib
import json
from collections import Counter

DIMENSIONS = ('story', 'art', 'system', 'polish')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def task_score(task, rules):
    if task['status'] is None:
        return None
    if rules.get('feature_branch_scoring') != 'status' and task['implementation_location'] == 'feature_branch' and task['status'] != 'not_started':
        return None
    return rules['status_factors'][task['status']] * 100


def weighted(tasks, rules):
    scores = [task_score(task, rules) for task in tasks]
    if not tasks or any(score is None for score in scores):
        return None
    return sum(t['weight'] * score for t, score in zip(tasks, scores)) / sum(t['weight'] for t in tasks)


def calculate(todo):
    rules = todo['rules']
    confirmed = rules['approval'] == 'confirmed'
    tasks = [t for t in todo['items'] if t['kind'] == 'task' and t['scope'] == 'demo']
    dimensions = []
    for dim in DIMENSIONS:
        relevant = [t for t in tasks if t['dimension'] == dim]
        unknown = [t['id'] for t in relevant if task_score(t, rules) is None]
        reasons = []
        if not confirmed:
            reasons.append('评分规则尚未确认')
        if unknown:
            reasons.append(f'{len(unknown)} 个任务的目标分支完成度待确认')
        value = weighted(relevant, rules) if dim != 'polish' else todo['manual_scores']['polish.manual']['value']
        manual = None
        ui_score = None
        if dim == 'art':
            ui_groups = set(rules.get('ui_group_ids', []))
            ui_tasks = [t for t in relevant if t['parent_id'] in ui_groups]
            other_tasks = [t for t in relevant if t['parent_id'] not in ui_groups]
            ui_score = weighted(ui_tasks, rules)
            other_score = weighted(other_tasks, rules)
            if not ui_tasks:reasons.append('请选择有效的 UI 任务大项')
            if not other_tasks:reasons.append('其他美术任务未配置')
            value = None if other_score is None or ui_score is None else other_score * (1-rules['art_ui_share']) + ui_score * rules['art_ui_share']
        elif dim == 'polish':
            manual = value
            if value is None:
                reasons.append('打磨手动分数待填写')
        if not confirmed:
            value = None
        share = rules['dimension_shares'][dim]
        dimensions.append({'id': dim, 'label': next(d['title'] for d in todo['dimensions'] if d['id']==dim), 'score': value, 'share': share, 'contribution': None if value is None else value*share, 'manual_score': manual, 'ui_score':ui_score, 'unknown_task_ids': unknown, 'missing_reasons': reasons})
    overall = None if any(d['score'] is None for d in dimensions) else sum(d['contribution'] for d in dimensions)
    return {'overall': overall, 'dimensions': dimensions, 'missing_reasons': [f'{d["label"]}：{reason}' for d in dimensions for reason in d['missing_reasons']]}


def group_status(children):
    if all(c['status'] == 'done' for c in children):
        return 'done'
    if all(c['status'] == 'not_started' for c in children):
        return 'not_started'
    if all(c['status'] == 'implemented_unverified' for c in children):
        return 'implemented_unverified'
    if all(c['status'] is None for c in children):
        return 'pending_confirmation'
    if any(c['status'] in ('in_progress', 'implemented_unverified', 'done') for c in children):
        return 'in_progress'
    return 'pending_confirmation'


def task_views(todo):
    groups = []
    for parent in todo['items']:
        if parent['kind'] != 'group':
            continue
        children = [t for t in todo['items'] if t['parent_id'] == parent['id']]
        groups.append({'id': parent['id'], 'title': parent['title'], 'dimension': parent['dimension'], 'scope': parent['scope'], 'status': group_status(children), 'score': weighted(children, todo['rules']) if todo['rules']['approval']=='confirmed' else None, 'weight': sum(t['weight'] for t in children), 'has_feature_branch': any(t['implementation_location']=='feature_branch' for t in children), 'children': [{k:t[k] for k in ('id','title','status','assessment','completion_criteria','weight','implementation_location')} for t in children]})
    return groups


def make_snapshot(todo, config):
    result = calculate(todo)
    evaluation = todo['evaluation']
    groups = task_views(todo)
    tasks = [t for t in todo['items'] if t['kind']=='task' and t['scope']=='demo']
    summaries = []
    for dim in result['dimensions']:
        remaining = [g['title'] for g in groups if g['scope']=='demo' and g['dimension']==dim['id'] and g['status']!='done'][:3]
        custom = evaluation['dimension_reviews'].get(dim['id'])
        fallback = '手动评分由开发者提供。' if dim['id']=='polish' else f'当前有 {len(dim["unknown_task_ids"])} 个目标分支任务待确认；依据静态实现与人工验收记录评估。'
        summaries.append({**dim, 'review': custom or fallback, 'remaining': remaining})
    snapshot = {
        'schema_version':'1.1.0', 'snapshot_id':'',
        'project': {'id':todo['project']['id'],'title':config['title'],'phase':todo['project']['phase'],'phase_label':config['phase_label']},
        'evaluated_at':evaluation['evaluated_at'], 'scope_version':todo['snapshot']['scope_version'], 'rules_version':todo['snapshot']['rules_version'],
        'sources': [s for s in todo['sources'] if s['kind']=='git'],
        'todo_sha256':hashlib.sha256(canonical(todo)).hexdigest(),
        'overall':result['overall'], 'dimensions':summaries, 'missing_reasons':result['missing_reasons'],
        'rules':todo['rules'], 'manual_scores':todo['manual_scores'],
        'groups':groups, 'task_counts':{'total':len(tasks),'remaining':sum(t['status']!='done' for t in tasks),'statuses':dict(Counter(t['status'] or 'pending_confirmation' for t in tasks))},
        'update':{'highlights':evaluation['highlights'],'change_reasons':evaluation['change_reasons'],'delta':None,'comparable':False},
        'method':'静态评估 + 开发者提供的验收记录；未运行游戏',
    }
    # Assessment time alone does not create development history.
    identity = {k:v for k,v in snapshot.items() if k not in ('evaluated_at','snapshot_id')}
    stable_todo = json.loads(canonical(todo))
    stable_todo['evaluation'].pop('evaluated_at', None)
    stable_todo['snapshot'].pop('date', None)
    identity['todo_sha256'] = hashlib.sha256(canonical(stable_todo)).hexdigest()
    snapshot['snapshot_id'] = hashlib.sha256(canonical(identity)).hexdigest()[:20]
    return snapshot


def compare(snapshot, previous):
    if previous is None:
        snapshot['update']['change_reasons'] = [{'type':'initial_baseline','text':'首次基线，尚无上次评估可比较。'}] + snapshot['update']['change_reasons']
        return
    comparable = all(snapshot[k]==previous[k] for k in ('scope_version','rules_version')) and snapshot['project']['phase']==previous['project']['phase']
    snapshot['update']['comparable'] = comparable
    a,b = snapshot['overall'],previous['overall']
    snapshot['update']['delta'] = a-b if comparable and a is not None and b is not None else None
    for key,kind,text in [('scope_version','demo_expansion','范围版本发生变化，前后口径不同。'),('rules_version','rule_change','评分规则版本发生变化，前后口径不同。')]:
        if snapshot[key]!=previous[key] and not any(r['type']==kind for r in snapshot['update']['change_reasons']):
            snapshot['update']['change_reasons'].append({'type':kind,'text':text})
