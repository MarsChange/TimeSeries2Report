"""Build an explicit, secret-free source bundle for the Stlite browser app."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'app.py': 'app.py',
    'utils/data_utils.py': 'utils/data_utils.py',
    'utils/prompt_engineering.py': 'utils/prompt_engineering.py',
    'utils/db_utils.py': 'utils/db_utils.py',
    'utils/browser_client.py': 'utils/browser_client.py',
    'samples/battery_time_series_for_test.pickle': 'battery_time_series_for_test.pickle',
    'samples/template_nca_description.jsonl': 'template_nca_description.jsonl',
}


def build():
    target = ROOT / 'docs/app/runtime.zip'
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for destination, source in FILES.items():
            entry = zipfile.ZipInfo(destination, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, (ROOT / source).read_bytes())
        archive.writestr('utils/__init__.py', '')
    print(f'Built {target.relative_to(ROOT)} ({len(FILES)} source/sample files; no .env or user database)')


if __name__ == '__main__':
    build()
