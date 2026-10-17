"""Fetch and verify the pinned upstream SO-101 MuJoCo model (TheRobotStudio/SO-ARM100).

The revision, file list and SHA-256 hashes live in ``assets.lock.json`` next to the package. ``fetch`` downloads
missing files into ``third_party/so101/`` and refuses any file whose hash differs from the lock. ``lock`` rewrites
the hashes from a fresh download (maintainer use only)."""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / 'assets.lock.json'
DEST = ROOT / 'third_party' / 'so101'


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _lock():
    return json.loads(LOCK.read_text())


def _url(lock, rel):
    return 'https://raw.githubusercontent.com/%s/%s/%s' % (lock['repo'], lock['revision'], rel)


def model_xml():
    """path of the verified upstream MJCF; raises if assets are missing or modified"""
    status = verify()
    if status['missing'] or status['bad']:
        raise FileNotFoundError('SO-101 assets missing or modified (%s). Run: python -m benchsim.assets fetch'
                                % ', '.join(status['missing'] + status['bad']))
    return DEST / _lock()['model']


def verify():
    lock = _lock(); missing, bad = [], []
    for rel, h in lock['files'].items():
        p = DEST / Path(rel).relative_to(lock['subdir']) if rel.startswith(lock['subdir']) else DEST / rel
        if not p.exists(): missing.append(rel)
        elif _sha(p) != h: bad.append(rel)
    return {'missing': missing, 'bad': bad}


def _local(lock, rel):
    return DEST / Path(rel).relative_to(lock['subdir']) if rel.startswith(lock['subdir']) else DEST / rel


def fetch(relock=False):
    lock = _lock()
    for rel, h in lock['files'].items():
        p = _local(lock, rel)
        if p.exists() and not relock and _sha(p) == h: continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(_url(lock, rel), timeout=60) as r: data = r.read()
        got = hashlib.sha256(data).hexdigest()
        if relock: lock['files'][rel] = got
        elif got != h: raise RuntimeError('hash mismatch for %s: got %s, lock %s' % (rel, got, h))
        p.write_bytes(data); print('fetched', rel, got[:12])
    if relock: LOCK.write_text(json.dumps(lock, indent=1) + '\n')
    print('SO-101 assets OK at', DEST, '(revision %s)' % lock['revision'][:12])


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'fetch'
    if cmd == 'fetch': fetch()
    elif cmd == 'lock': fetch(relock=True)
    elif cmd == 'verify':
        s = verify(); print(json.dumps(s, indent=1)); sys.exit(1 if s['missing'] or s['bad'] else 0)
    else: sys.exit('usage: python -m benchsim.assets [fetch|verify|lock]')
