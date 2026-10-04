#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate progress data only; never reads or executes the game project."""
import json
import math
import sys
from collections import Counter
from pathlib import Path


def validate(data):
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    def index(records, label):
        ids = [record['id'] for record in records]
        check(len(ids) == len(set(ids)), f'{label}: duplicate IDs')
        return {record['id']: record for record in records}

    check(data['schema_version'] in {'1.2.0'}, 'unsupported schema version')
    items = index(data['items'], 'items')
    evidence = index(data['evidence'], 'evidence')
    sources = index(data['sources'], 'sources')
    plans = index(data['verification_plans'], 'verification plans')
    dimensions = index(data['dimensions'], 'dimensions')
    check(data['project']['target_source'] in sources, 'missing target source')
    states = set(data['rules']['status_factors'])
    check(states == {'not_started', 'in_progress', 'implemented_unverified', 'done'}, 'invalid status factors')
    check(math.isclose(sum(data['rules']['dimension_shares'].values()), 1), 'dimension shares must sum to 1')
    check(0 < data['rules']['art_ui_share'] < 1, 'UI share must be between 0 and 1')
    check(all(0 <= value <= 1 for value in data['rules']['status_factors'].values()), 'invalid status factor')
    for item in items.values():
        id = item['id']
        check(item['kind'] in {'group', 'task', 'manual'}, f'{id}: invalid kind')
        check(item['scope'] in {'demo', 'future'}, f'{id}: invalid scope')
        check(item['dimension'] in dimensions, f'{id}: unknown dimension')
        check(item['implementation_location'] in {None, 'main', 'feature_branch'}, f'{id}: invalid location')
        check(item['status'] is None or item['status'] in states, f'{id}: invalid status')
        check(all(e in evidence for e in item['evidence_ids']), f'{id}: broken evidence reference')
        check(all(v in plans for v in item['verification_ids']), f'{id}: broken verification reference')
        if item['kind'] == 'task':
            parent = items.get(item['parent_id'])
            check(parent is not None and parent['kind'] == 'group', f'{id}: task must have a group parent')
            if parent:
                check(parent['dimension'] == item['dimension'] and parent['scope'] == item['scope'], f'{id}: parent dimension/scope mismatch')
            check(isinstance(item['weight'], (int, float)) and not isinstance(item['weight'], bool) and item['weight'] > 0, f'{id}: invalid weight')
            check(bool(item['completion_criteria']), f'{id}: missing completion criteria')
            expected = 'pending_confirmation' if item['status'] is None else 'assessed'
            check(item['assessment'] == expected, f'{id}: status/assessment mismatch')
            if item['status'] == 'done':
                check(any(evidence[e]['kind'] == 'user_verification' for e in item['evidence_ids'] if e in evidence), f'{id}: done needs user verification evidence')
        else:
            check(item['parent_id'] is None and item['weight'] is None and item['status'] is None, f'{id}: group/manual cannot store task score fields')
            check(item['assessment'] == ('aggregate' if item['kind'] == 'group' else 'manual'), f'{id}: invalid assessment')
        if item['kind'] == 'group':
            children = [i for i in items.values() if i['parent_id'] == id]
            check(bool(children), f'{id}: empty group')
            budget = data['group_budgets'].get(id)
            check(budget is not None and math.isclose(sum(i['weight'] for i in children), budget), f'{id}: child weights do not match reserved budget')
    check(set(data['group_budgets']) == {i['id'] for i in items.values() if i['kind'] == 'group'}, 'group budget IDs mismatch')
    check(set(data['manual_scores']) == {i['id'] for i in items.values() if i['kind'] == 'manual'}, 'manual score IDs mismatch')
    for id, score in data['manual_scores'].items():
        value = score['value']
        check(value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100), f'{id}: invalid manual score')
        if value is not None:
            check(score['updated_by'] == 'user' and bool(score['updated_at']), f'{id}: manual score needs user provenance')
    for record in evidence.values():
        check(record['source'] in sources, f"{record['id']}: missing evidence source")
    for plan in plans.values():
        check(plan['source'] in sources and plan['executor'] == 'user', f"{plan['id']}: invalid verification source/executor")
        check(plan['result'] in {None, 'passed', 'failed'}, f"{plan['id']}: invalid result")
        check(plan['result'] is None or bool(plan['evidence']), f"{plan['id']}: result needs evidence")
    for section in ['candidate_notes', 'pending_decisions']:
        for record in data[section]:
            check(all(id in items for id in record['related_ids']), f"{record['id']}: broken related ID")
    return errors


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('todo.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        from scripts.schema_check import validate_schema
        schema = json.loads(path.with_name('todo.schema.json').read_text(encoding='utf-8'))
        errors = validate_schema(data, schema)
        if not errors:
            errors = validate(data)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f'Invalid data: {error}', file=sys.stderr)
        return 1
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    counts = Counter(item['kind'] for item in data['items'])
    print(f"Valid: {counts['group']} groups, {counts['task']} tasks, {counts['manual']} manual scores")
    print('Scoring rules: ' + data['rules']['approval'] + '; no progress percentage calculated')
    return 0


if __name__ == '__main__':
    sys.exit(main())
