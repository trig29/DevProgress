#!/usr/bin/env python3
"""Stamp a deployment artifact; never marks local history as successfully published."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory', type=Path, default=Path('site'))
parser.add_argument('--url', required=True)
args = parser.parse_args()
p = args.directory/'data'/'current.json'
current = json.loads(p.read_text())
# This timestamp is exposed only if the artifact deployment actually succeeds.
current['published_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
current['publication_url'] = args.url
p.write_text(json.dumps(current, ensure_ascii=False, indent=2)+'\n')
