"""Download pinned browser dependencies into the Pages artifact (never into Git)."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / 'docs/app/vendor'
STLITE = 'https://cdn.jsdelivr.net/npm/@stlite/browser@0.85.1'
PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.6/full'


def read(url):
    for attempt in range(4):
        try:
            with urlopen(url, timeout=90) as response:
                return response.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def download(job):
    url, target, digest = job
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and digest and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return
    data = read(url)
    if digest and hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f'Checksum mismatch: {target.name}')
    target.write_bytes(data)


def build():
    manifest = json.loads(read('https://data.jsdelivr.com/v1/package/npm/@stlite/browser@0.85.1/flat'))
    jobs = []
    for item in manifest['files']:
        name = item['name']
        if name.startswith('/build/') and not name.endswith('.map'):
            jobs.append((STLITE + name, ROOT / 'stlite' / name.removeprefix('/build/'),
                         base64.b64decode(item['hash']).hex()))
    lock_data = read(PYODIDE + '/pyodide-lock.json')
    lock = json.loads(lock_data)
    target = ROOT / 'pyodide'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'pyodide-lock.json').write_bytes(lock_data)
    for name in ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip']:
        jobs.append((PYODIDE + '/' + name, target / name, None))
    seeds = 'micropip packaging numpy matplotlib requests sqlite3 pandas altair cachetools protobuf typing-extensions pyodide-http fastparquet'.split()
    packages = lock['packages']
    pending, selected = list(seeds), set()
    while pending:
        name = pending.pop().lower().replace('_', '-')
        # Pyodide uses both hyphens and underscores in package keys.
        key = next(k for k in packages if k.lower().replace('_', '-') == name)
        if key in selected:
            continue
        selected.add(key)
        pending.extend(packages[key]['depends'])
    for name in sorted(selected):
        item = packages[name]
        jobs.append((PYODIDE + '/' + item['file_name'], target / item['file_name'], item['sha256']))
    wheels = []
    for package, version in [('python-dotenv', '1.1.1'), ('reportlab', '4.4.9'), ('blinker', '1.9.0'), ('tenacity', '9.1.2')]:
        metadata = json.loads(read(f'https://pypi.org/pypi/{package}/{version}/json'))
        wheel = next(item for item in metadata['urls'] if item['filename'].endswith('none-any.whl'))
        jobs.append((wheel['url'], ROOT / 'wheels' / wheel['filename'], wheel['digests']['sha256']))
        wheels.append('vendor/wheels/' + wheel['filename'])
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download, jobs))
    (ROOT / 'requirements.json').write_text(json.dumps(wheels))
    print(f'Vendored {len(jobs)} pinned runtime assets; {len(selected)} Pyodide packages.', flush=True)


if __name__ == '__main__':
    build()
