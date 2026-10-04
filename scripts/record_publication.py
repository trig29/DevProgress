#!/usr/bin/env python3
"""After verifying a deployed snapshot, record its actual artifact timestamp locally."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', required=True)
args = parser.parse_args()
with urlopen(args.url.rstrip('/')+'/data/current.json', timeout=20) as response:
    published = json.load(response)
p = ROOT/'history'/'snapshots.json'
history = json.loads(p.read_text())
if not history['snapshots'] or history['snapshots'][-1]['snapshot_id'] != published['snapshot_id']:
    parser.exit(1, 'Deployed snapshot does not match latest local evaluation\n')
if not published.get('published_at'):
    parser.exit(1, 'Deployed artifact has no publication timestamp\n')
history['snapshots'][-1]['published_at'] = published['published_at']
p.write_text(json.dumps(history, ensure_ascii=False, indent=2)+'\n')
print('Verified and recorded publication of '+published['snapshot_id'])
