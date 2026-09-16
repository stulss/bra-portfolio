"""Sync the public ritual summary from Notion before building the site."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DATA_SOURCE_ID = '3d385516-e6ec-811e-95b3-000b46775778'
NOTION_VERSION = '2026-03-11'
STATUS_MAP = {'done': '실천했다', 'partial': '일부 실천했다', 'missed': '못 했다'}


def property_text(prop: dict) -> str:
    kind = prop.get('type')
    if kind in ('title', 'rich_text'):
        return ''.join(item.get('plain_text', '') for item in prop.get(kind, [])).strip()
    if kind == 'select':
        return (prop.get('select') or {}).get('name', '').strip()
    if kind == 'date':
        return (prop.get('date') or {}).get('start', '').split('T', 1)[0]
    return ''


def query_rows(token: str) -> list[dict]:
    rows, cursor = [], None
    while True:
        body = {'page_size': 100, 'sorts': [{'property': '날짜', 'direction': 'ascending'}]}
        if cursor:
            body['start_cursor'] = cursor
        request = Request(
            f'https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query',
            data=json.dumps(body).encode(),
            headers={
                'Authorization': f'Bearer {token}',
                'Notion-Version': NOTION_VERSION,
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        try:
            with urlopen(request, timeout=30) as response:
                page = json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')[:300]
            raise RuntimeError(f'노션 응답 오류 {exc.code}: {detail}') from exc
        except URLError as exc:
            raise RuntimeError(f'노션 연결 실패: {exc.reason}') from exc
        for item in page.get('results', []):
            props = item.get('properties', {})
            rows.append({name: property_text(props.get(name, {})) for name in ('날짜', '구분', '실천 및 행동')})
        if not page.get('has_more'):
            return rows
        cursor = page.get('next_cursor')


def closing_record(action: str) -> tuple[str, str]:
    match = re.search(r'실천\((done|partial|missed)\):\s*(.*?)(?:\s*\\?\|\s*기여:|$)', action, re.S)
    if not match:
        return '기록 없음', ''
    return STATUS_MAP[match.group(1)], re.sub(r'<br\s*/?>', ' ', match.group(2)).strip()


def infer_ability(sentence: str) -> str:
    groups = (
        ('대인관계력', ('동료', '대화', '말을', '의견', '질문', '물어', '감사', '칭찬', '함께', '관계')),
        ('자기조절력', ('호흡', '순서', '차분', '당황', '조급', '반응', '페이스', '알림', '쉬는 시간')),
        ('자기동기력', ('끝까지', '집중', '포기', '이해', '목표', '메모', '기록', '마무리', '다시')),
    )
    scores = [(sum(word in sentence for word in words), ability) for ability, words in groups]
    score, ability = max(scores)
    return ability if score else '자기동기력'


def rows_to_rituals(rows: list[dict], existing: list[dict]) -> list[dict]:
    grouped: dict[str, dict[str, str]] = {}
    for row in rows:
        record_date, kind = row.get('날짜', ''), row.get('구분', '')
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', record_date) and kind in ('아침 리추얼', '마무리 리추얼'):
            grouped.setdefault(record_date, {})[kind] = row.get('실천 및 행동', '')
    current = {row['date']: row for row in existing}
    synced = []
    for record_date, sessions in sorted(grouped.items()):
        status, sentence = closing_record(sessions.get('마무리 리추얼', ''))
        previous = current.get(record_date, {})
        evidence = previous.get('evidence') or ({infer_ability(sentence): sentence} if sentence else {})
        synced.append({
            'date': record_date,
            'sessions': len(sessions),
            'status': status,
            'evidence': evidence,
            'source': f'노션 리추얼 기록 DB · {record_date} 본인 기록',
        })
    for record_date, row in current.items():
        if record_date not in grouped:
            synced.append(row)
    return sorted(synced, key=lambda row: row['date'])


def write_json(path: Path, value: object) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8-sig') == content:
        return
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(content, encoding='utf-8', newline='\n')
    temporary.replace(path)


def notion_token() -> str | None:
    token = os.environ.get('NOTION_TOKEN') or os.environ.get('NOTION_API_KEY') or os.environ.get('NOTION_API_TOKEN')
    if token or os.name != 'nt':
        return token
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            return winreg.QueryValueEx(key, 'NOTION_TOKEN')[0]
    except FileNotFoundError:
        return None


def sync(folder: Path) -> str:
    token = notion_token()
    if not token:
        return 'Notion sync skipped: NOTION_TOKEN 환경변수가 없습니다.'
    ritual_path, profile_path = folder / 'ritual.json', folder / 'profile.json'
    existing = json.loads(ritual_path.read_text(encoding='utf-8-sig'))
    profile = json.loads(profile_path.read_text(encoding='utf-8-sig'))
    rows = query_rows(token)
    if not rows:
        raise RuntimeError('노션 리추얼 기록 DB가 비어 있어 기존 입력을 보존했습니다.')
    rituals = rows_to_rituals(rows, existing)
    if rituals:
        profile['as_of'] = max(profile['as_of'], rituals[-1]['date'])
    added = len({row['date'] for row in rituals} - {row['date'] for row in existing})
    previous = {row['date']: row for row in existing}
    changed = sum(previous[row['date']] != row for row in rituals if row['date'] in previous)
    write_json(ritual_path, rituals)
    write_json(profile_path, profile)
    return f'Notion sync OK: {len(rituals)}일 ({added}일 추가, {changed}일 갱신)'
