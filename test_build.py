"""Run with python test_build.py. All fixtures stay inside temporary folders."""
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from urllib.parse import urlsplit
from build import ROOT, build, load, aggregate
from notion_sync import closing_record, infer_ability, rows_to_rituals


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
    status, sentence = closing_record('실천(partial): 동료에게 의견을 물었다. | 기여: 도움을 받았다.')
    assert status == '일부 실천했다' and sentence == '동료에게 의견을 물었다.'
    assert infer_ability(sentence) == '대인관계력'
    synced = rows_to_rituals([
        {'날짜': '2026-09-17', '구분': '아침 리추얼', '실천 및 행동': '첫행동: 시작'},
        {'날짜': '2026-09-17', '구분': '마무리 리추얼', '실천 및 행동': '실천(done): 10초간 호흡하고 순서를 적었다. | 기여: 없음'},
    ], [])
    assert synced == [{'date': '2026-09-17', 'sessions': 2, 'status': '실천했다',
                       'evidence': {'자기조절력': '10초간 호흡하고 순서를 적었다.'},
                       'source': '노션 리추얼 기록 DB · 2026-09-17 본인 기록'}]
    with TemporaryDirectory(prefix='bra-check-') as temp:
        base = Path(temp)
        src = base / 'input'
        shutil.copytree(ROOT / 'input', src)
        p, rows, attendance, tasks = load(src)
        m, candidates = aggregate(p, rows, attendance, tasks)
        assert m['record_days'] == len(rows) and m['sessions'] == sum(r['sessions'] for r in rows)
        assert {c['ability'] for c in candidates} == {'자기조절력', '대인관계력', '자기동기력'}
        assert all(c['text'].count('.') >= 2 for c in candidates)
        fixture = [dict(rows[0], status='못 했다'), dict(rows[1], status='일부 실천했다'), dict(rows[2], status='기록 없음')]
        assert aggregate(p, fixture, [], [])[0]['recoveries_at_next_record'] == 1
        build(src, base / 'a'); first = hashes(base / 'a')
        check_links(base / 'a')
        resume = (base / 'a/documents.html').read_text(encoding='utf-8')
        site = (base / 'a/index.html').read_text(encoding='utf-8')
        paper = (base / 'a/paper.html').read_text(encoding='utf-8')
        from html import escape
        for entry in p.get('employment', []) + p.get('education', []) + p.get('qualifications', []):
            assert escape(entry['organization']) in resume
            assert escape(entry['period']) in resume
        assert [entry['title'].split('번')[0] for entry in p['career']] == ['10', '13']
        assert '9번 ·' not in resume and '11번 ·' not in resume
        for section in p['cover_letter']:
            assert escape(section['title']) in resume
            assert escape(section['body']) in resume
        for entry in p['employment']:
            assert all(escape(detail) in resume for detail in entry['details'])
        for growth in p['ability_growth']:
            assert escape(growth['ability']) in site
            assert escape(growth['before']) in site
            assert escape(growth['practice']) in site
            assert escape(growth['now']) in site
        assert f'mailto:{p["email"]}' in site
        assert '미확인' not in site
        assert all(text in site for text in ('일이 한꺼번에 들어오면', '먼저 멈춥니다.', '처리 순서를 적습니다.'))
        assert '대표작은 10번 과제 하나만 실었습니다.' in site
        assert '무료 AI 도구에 익숙해지기 위한 가벼운 연습' in site
        assert '완료한 프로젝트는 10번 하나입니다.' not in site
        assert '내용 검토 중입니다.' not in site
        assert '<article class="paper">' in paper and '<table>' in paper
        assert '<h1>반복해서 고치게 하면 정말 덜 고치게 되는가</h1>' in paper
        assert '<strong>주 가설은 기각됐다.</strong>' in paper
        assert '<td>정규화 문자 편집거리 <code>lev(a,b)/max(|a|,|b|)</code>, 0~1</td>' in paper
        assert '<pre class="paper-text">' not in paper
        assert not re.search(r'20\d{2}(?:[-./]\d{1,2})?', site), '소개 사이트에 날짜가 노출됨'
        assert '날짜별 기록' not in site
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
        subprocess.run([sys.executable, '-X', 'utf8', str(fresh / 'build.py'), '--no-sync', '--input', str(fresh / 'input'), '--output', str(fresh / 'again')], check=True)
        assert hashes(fresh / 'preview') == hashes(fresh / 'again')
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        assert hashlib.sha256(package().read_bytes()).hexdigest() == digest
        print('PASS: deterministic files/ZIP, fresh-folder run, metrics, invalid inputs, escaping, approval boundary')


if __name__ == '__main__':
    run()
