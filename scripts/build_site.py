#!/usr/bin/env python3
"""Validate Todo, append an immutable evaluation and export the static website."""
import argparse
import copy
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validate_todo import validate
from schema_check import validate_schema
from progress import canonical, make_snapshot, compare


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def checked(value, schema):
    errors = validate_schema(value, schema)
    if errors:
        raise ValueError('\n'.join(errors))


def build(project=ROOT, output=None, now=None):
    project = Path(project)
    output = Path(output) if output else project/'site'
    if output.resolve() == project.resolve() or project.resolve().is_relative_to(output.resolve()):
        raise ValueError('Output must not replace the project or its parent')
    if output.exists() and not (output/'.devprogress-output').exists():
        raise ValueError('Refusing to replace a directory not created by this builder')
    todo = read(project/'todo.json')
    checked(todo, read(project/'todo.schema.json'))
    errors = validate(todo)
    if errors:
        raise ValueError('\n'.join(errors))
    config = read(project/'site.config.json')
    for source in todo['sources']:
        if source['kind']=='git' and source.get('dirty'):
            raise ValueError('Public evaluation must use a committed baseline; record uncommitted changes separately')
    for record in todo['evidence']:
        for path in record['paths']:
            if Path(path).is_absolute() or path.startswith(('file:', 'C:\\')) or '..' in Path(path).parts:
                raise ValueError('Evidence paths must be repository-relative')
    history_path = project/'history'/'snapshots.json'
    history = read(history_path) if history_path.exists() else {'schema_version':'1.0.0','snapshots':[]}
    checked(history, read(project/'schemas'/'history.schema.json'))
    snapshot = make_snapshot(todo, config)
    latest = history['snapshots'][-1] if history['snapshots'] else None
    generated_at = now or datetime.now(ZoneInfo(config['timezone'])).isoformat(timespec='seconds')
    changed = latest is None or latest['snapshot_id'] != snapshot['snapshot_id']
    if changed:
        compare(snapshot, latest)
        snapshot['generated_at'] = generated_at
        snapshot['published_at'] = None
        history['snapshots'].append(copy.deepcopy(snapshot))
    else:
        fresh_time, fresh_hash = snapshot['evaluated_at'], snapshot['todo_sha256']
        snapshot = copy.deepcopy(latest)
        snapshot['evaluated_at'], snapshot['todo_sha256'] = fresh_time, fresh_hash
        snapshot['generated_at'] = generated_at
    # Local builds are never a claim that this evaluation has been deployed.
    snapshot['published_at'] = None
    snapshot['publication_url'] = config['publication']['url']
    checked(snapshot, read(project/'schemas'/'current.schema.json'))
    checked(history, read(project/'schemas'/'history.schema.json'))
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.devprogress-build-', dir=output.parent))
    try:
        shutil.copytree(project/'web', staging, dirs_exist_ok=True)
        write(staging/'data'/'current.json', snapshot)
        write(staging/'data'/'history.json', history)
        write(staging/'data'/'todo.json', todo)
        shutil.copy2(project/'todo.schema.json', staging/'data'/'todo.schema.json')
        shutil.copytree(project/'schemas', staging/'data'/'schemas')
        (staging/'.nojekyll').touch()
        (staging/'.devprogress-output').touch()
        # No source docs, local config, skill installation or game files are exported.
        allowed = {'index.html','assets','data','.nojekyll','.devprogress-output'}
        if set(p.name for p in staging.iterdir()) != allowed:
            raise ValueError('Unexpected file in deployment output')
        # Save history only after all validation/export steps have succeeded.
        write(history_path, history)
        if output.exists():
            shutil.rmtree(output)
        staging.rename(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return snapshot, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        snapshot, changed = build(args.project, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Build failed: {error}\n')
    print(f"Built {snapshot['project']['title']}: {snapshot['snapshot_id']}")
    print('History: '+('new evaluation recorded' if changed else 'unchanged (idempotent)'))
    print('Overall: '+('评估待完善' if snapshot['overall'] is None else f"{snapshot['overall']:.1f}%"))
    print('Local output only; not published.')


if __name__ == '__main__':
    main()
