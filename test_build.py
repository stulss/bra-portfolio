"""Run with python test_build.py. All fixtures stay inside temporary folders."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from urllib.parse import urlsplit
from build import ROOT, build, load, aggregate


def hashes(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}


def save(folder: Path, name: str, value: object) -> None:
    (folder / f'{name}.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def rejected(folder: Path, output: Path, publish: bool = False) -> None:
    try:
        build(folder, output, publish)
    except ValueError:
        return
    raise AssertionError('Invalid input or unapproved publication was accepted')


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs = dict(attrs)
        if 'id' in attrs: self.ids.add(attrs['id'])
        if tag in ('a', 'link') and 'href' in attrs: self.links.append(attrs['href'])


def check_links(folder: Path) -> None:
    parsed = {}
    for path in folder.glob('*.html'):
        page = Links(); page.feed(path.read_text(encoding='utf-8')); parsed[path.name] = page
    for filename, page in parsed.items():
        for link in page.links:
            parts = urlsplit(link)
            if parts.scheme: continue
            target = parts.path or filename
            assert (folder / target).is_file(), link
            if parts.fragment: assert parts.fragment in parsed[target].ids, link


def run() -> None:
    with TemporaryDirectory(prefix='bra-check-') as temp:
        base = Path(temp)
        src = base / 'input'
        shutil.copytree(ROOT / 'input', src)
        p, rows, attendance, tasks = load(src)
        m, candidates = aggregate(p, rows, attendance, tasks)
        assert m['record_days'] == len(rows) and m['sessions'] == sum(r['sessions'] for r in rows)
        assert {c['ability'] for c in candidates} == {'자기조절력', '대인관계력', '자기동기력'}
        fixture = [dict(rows[0], status='못 했다'), dict(rows[1], status='일부 실천했다'), dict(rows[2], status='기록 없음')]
        assert aggregate(p, fixture, [], [])[0]['recoveries_at_next_record'] == 1
        build(src, base / 'a'); first = hashes(base / 'a')
        check_links(base / 'a')
        build(src, base / 'a'); assert first == hashes(base / 'a')
        build(src, base / 'b'); assert first == hashes(base / 'b')
        rejected(src, base / 'public', True)
        broken = deepcopy(rows); broken.append(broken[0]); save(src, 'ritual', broken)
        rejected(src, base / 'bad')
        broken = deepcopy(rows); broken[0]['sessions'] = True; save(src, 'ritual', broken)
        rejected(src, base / 'bad')
        broken = deepcopy(rows); broken[0]['date'] = '2026-02-30'; save(src, 'ritual', broken)
        rejected(src, base / 'bad')
        save(src, 'ritual', rows)
        save(src, 'attendance', [{'date': rows[0]['date'], 'attended': 'false', 'source': 'test'}])
        rejected(src, base / 'bad'); save(src, 'attendance', attendance)
        approved = deepcopy(p)
        approved.update(human_lines_confirmed=True, privacy_reviewed=True, facts_reviewed=True, app_due='2026-10-01', headline='테스트한 사람')
        for s in approved['story']: s['approved'] = True
        approved['story'][0]['body'] = '<script>alert(1)</script>'
        save(src, 'profile', approved)
        build(src, base / 'public', True)
        html = (base / 'public/index.html').read_text(encoding='utf-8')
        assert '<script>alert' not in html and '&lt;script&gt;' in html
        assert not (base / 'public/candidates.json').exists()
        assert 'approved' not in html
        rejected(src, base / 'public', True)
        approved['story'][0]['approved'] = False; save(src, 'profile', approved)
        rejected(src, base / 'no-approval', True)
        # Exercise the actual distributable, without importing the original source folder.
        from package import package
        zip_path = package()
        with ZipFile(zip_path) as archive:
            assert archive.testzip() is None
            assert all(not info.flag_bits & 1 for info in archive.infolist())
            fresh = base / 'extracted'; archive.extractall(fresh)
        subprocess.run([sys.executable, '-X', 'utf8', str(fresh / 'build.py'), '--input', str(fresh / 'input'), '--output', str(fresh / 'again')], check=True)
        assert hashes(fresh / 'preview') == hashes(fresh / 'again')
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        assert hashlib.sha256(package().read_bytes()).hexdigest() == digest
        print('PASS: deterministic files/ZIP, fresh-folder run, metrics, invalid inputs, escaping, approval boundary')


if __name__ == '__main__':
    run()
