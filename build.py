"""BR-A: deterministic, dependency-free local publisher. Python 3.11+."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
from html import escape
import json
from pathlib import Path
import re
from string import Template

ROOT = Path(__file__).resolve().parent
ABILITIES = ('자기조절력', '대인관계력', '자기동기력')
STATUSES = ('실천했다', '일부 실천했다', '못 했다', '기록 없음')
MARKS = {'실천했다': 'full', '일부 실천했다': 'half', '못 했다': 'none', '기록 없음': 'blank'}


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label}: 비어 있지 않은 문자열이 필요합니다.')
    return value


def day(value: object, label: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'{label}: YYYY-MM-DD가 필요합니다.')
    return date.fromisoformat(value)


def load(folder: Path) -> tuple[dict, list, list, list]:
    values = [json.loads((folder / f'{name}.json').read_text(encoding='utf-8-sig'))
              for name in ('profile', 'ritual', 'attendance', 'tasks')]
    profile, rituals, attendance, tasks = values
    if not isinstance(profile, dict) or any(not isinstance(v, list) for v in values[1:]):
        raise ValueError('profile는 객체, 나머지 입력은 배열이어야 합니다.')
    start, end = day(profile['course_start'], '시작일'), day(profile['as_of'], '기준일')
    if start > end:
        raise ValueError('시작일은 기준일보다 늦을 수 없습니다.')
    for name in ('name', 'headline', 'intro', 'email'):
        text(profile[name], name)
    if not re.fullmatch(r'[^\s@<>"\r\n]+@[^\s@<>"\r\n]+\.[^\s@<>"\r\n]+', profile['email']):
        raise ValueError('유효한 공개 이메일이 필요합니다.')
    for rows, key in ((rituals, 'date'), (attendance, 'date'), (tasks, 'id')):
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('입력 행은 객체여야 합니다.')
            identifier = text(row[key], key)
            if identifier in seen:
                raise ValueError(f'중복 입력: {identifier}')
            seen.add(identifier)
            if not start <= day(row['date'], '기록일') <= end:
                raise ValueError('기록일은 과정 시작일~기준일 안이어야 합니다.')
            text(row['source'], '출처')
    for row in rituals:
        if type(row['sessions']) is not int or not 1 <= row['sessions'] <= 2:
            raise ValueError('sessions는 1 또는 2입니다.')
        if row['status'] not in STATUSES or not isinstance(row['evidence'], dict):
            raise ValueError('리추얼 상태 또는 근거 형식 오류')
        for ability, evidence in row['evidence'].items():
            if ability not in ABILITIES:
                raise ValueError('알 수 없는 능력')
            text(evidence, '근거')
    for rows, field in ((attendance, 'attended'), (tasks, 'submitted')):
        for row in rows:
            if type(row[field]) is not bool:
                raise ValueError(f'{field}는 true/false여야 합니다.')
    for row in tasks:
        if row['ability'] not in ABILITIES:
            raise ValueError('과제 능력 오류')
        for key in ('title', 'situation', 'action', 'result'):
            text(row[key], key)
    for scene in profile['story']:
        day(scene['date'], '장면일')
        if scene['date'] > profile['as_of'] or scene['ability'] not in ABILITIES:
            raise ValueError('미래 장면 또는 능력 오류')
        for key in ('title', 'body', 'source'):
            text(scene[key], key)
        if type(scene['approved']) is not bool:
            raise ValueError('approved는 true/false여야 합니다.')
    return profile, sorted(rituals, key=lambda r: r['date']), attendance, tasks


def aggregate(profile: dict, rows: list, attendance: list, tasks: list) -> tuple[dict, list]:
    weeks = {((day(r['date'], 'date') - day(profile['course_start'], 'start')).days // 7) + 1 for r in rows}
    recoveries = sum(a['status'] == '못 했다' and b['status'] in STATUSES[:2]
                     for a, b in zip(rows, rows[1:]))
    metrics = {'period': [rows[0]['date'], rows[-1]['date']] if rows else [],
               'record_days': len(rows), 'sessions': sum(r['sessions'] for r in rows),
               'recorded_weeks': len(weeks), 'planned_weeks': 13,
               'recoveries_at_next_record': recoveries,
               'recovery_pairs': [[a['date'], b['date']] for a, b in zip(rows, rows[1:])
                                  if a['status'] == '못 했다' and b['status'] in STATUSES[:2]],
               'attendance': None if not attendance else {'attended': sum(r['attended'] for r in attendance), 'observed': len(attendance)},
               'submissions': None if not tasks else {'submitted': sum(r['submitted'] for r in tasks), 'observed': len(tasks)},
               'sources': sorted({r['source'] for r in rows})}
    candidates = []
    for row in rows:
        for ability in ABILITIES:
            if ability in row['evidence']:
                evidence = row['evidence'][ability]
                identifier = hashlib.sha256(f"{row['date']}|{ability}|{evidence}".encode()).hexdigest()[:16]
                candidates.append({'id': identifier, 'date': row['date'], 'ability': ability,
                                   'text': f"{row['date']} 기록에서 돌아본 {ability}: {evidence}",
                                   'evidence': evidence, 'source': row['source'], 'approved': False})
    return metrics, candidates


def status_mark(status: str | None) -> str:
    """상태를 색이 아니라 채움 모양으로 표시한다. 상태를 모르면 아무것도 그리지 않는다."""
    if status not in MARKS:
        return ''
    return (f'<span class="mark mark-{MARKS[status]}" aria-hidden="true"></span>'
            f'{escape(status)}')


def scene_html(scene: dict, status: str | None) -> str:
    mark = status_mark(status)
    return (f'<article class="scene"><div class="scene-rail">'
            f'<time class="date" datetime="{escape(scene["date"])}">{escape(scene["date"])}</time>'
            + (f'<span class="scene-status">{mark}</span>' if mark else '')
            + f'<span class="scene-ability">{escape(scene["ability"])}</span></div>'
            f'<div class="scene-body"><h3>{escape(scene["title"])}</h3><p>{escape(scene["body"])}</p>'
            f'<p class="source">근거: {escape(scene["source"])}</p></div></article>')


def hero_pair(profile: dict, metrics: dict, statuses: dict) -> str:
    """첫 화면에 못 한 날과 다시 기록한 날을 실제 기록 그대로 나란히 둔다."""
    scenes = {s['date']: s for s in profile['story']}
    pair = next((p for p in metrics['recovery_pairs'] if all(d in scenes for d in p)), None)
    if pair is None:
        return ''
    entries = ''.join(
        f'<article class="entry{"" if d == pair[0] else " entry-return"}"><p class="entry-meta">'
        f'<time datetime="{escape(d)}">{escape(d)}</time>{status_mark(statuses.get(d))}</p>'
        f'<p class="entry-line">{escape(scenes[d]["title"])}</p></article>'
        + ('<p class="retry-join">다음 날, 다시 기록했습니다.</p>' if d == pair[0] else '')
        for d in pair)
    return f'<div class="retry">{entries}</div>'


def document(profile: dict, story: str, draft: str) -> str:
    labels = {'period': '기간', 'title': '과제', 'ability': '능력', 'situation': '상황', 'action': '행동', 'result': '결과'}
    rows = ''.join('<tr>' + ''.join(f'<td data-label="{labels[k]}">{escape(str(row[k]))}</td>' for k in
                                  labels) + '</tr>'
                   for row in profile['career'])
    return (f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(profile["name"])} · 지원 문서</title><link rel="stylesheet" href="style.css">'
            '<body><main class="document"><p class="no-print"><a href="index.html">← 소개 사이트</a></p>'
            '<button class="print-button no-print" onclick="window.print()">인쇄 / PDF 저장</button>'
            f'{draft}<section><h1 style="font-size:40px;letter-spacing:-2px">이력서</h1><h2>{escape(profile["name"])}</h2>'
            f'<p>{escape(profile["email"])}</p><p>{escape(profile["headline"])}</p>'
            '<h3>프로젝트 경험</h3><ul>' + ''.join(f'<li>{escape(r["period"])} · {escape(r["title"])}</li>' for r in profile['career']) +
            '</ul><p>학력·직장 경력은 정확한 기관명과 기간 확인 후 추가합니다.</p></section>'
            f'<section><h2>자기소개서</h2>{story}</section><section><h2>경력기술서</h2>'
            '<p>과제 수행 경험 기준. 외부 고용 경력이나 공식 제출 확인을 의미하지 않습니다.</p>'
            '<table><thead><tr><th>기간</th><th>과제</th><th>능력</th><th>상황</th><th>행동</th><th>결과</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></section></main></body></html>')


def build(folder: Path, output: Path, publish: bool = False) -> dict:
    profile, rows, attendance, tasks = load(folder)
    if publish:
        if not all(profile.get(k) is True for k in ('human_lines_confirmed', 'privacy_reviewed', 'facts_reviewed')):
            raise ValueError('직접 작성 문장·개인정보·사실 확인이 필요합니다.')
        if not profile['headline'].endswith('한 사람') or not profile.get('app_due'):
            raise ValueError('한 줄 소개 형식과 앱 예정일을 확인하세요.')
        if not profile['story'] or any(s['approved'] is not True for s in profile['story']):
            raise ValueError('본문에 미승인 장면이 있습니다.')
    metrics, candidates = aggregate(profile, rows, attendance, tasks)
    statuses = {r['date']: r['status'] for r in rows}
    story = ''.join(scene_html(s, statuses.get(s['date'])) for s in profile['story'])
    if metrics['recovery_pairs']:
        pairs = ', '.join(' → '.join(pair) for pair in metrics['recovery_pairs'])
        story += f'<p class="recovery">고난 뒤 재시도의 기록: {escape(pairs)}. 미실천 뒤 다음 기록일에 일부 또는 전체 실천을 남긴 날짜 쌍입니다. <a href="#numbers">숫자로 보기</a></p>'
    draft = '' if publish else '<p class="banner">작성자 검토용 초안입니다. 본문과 한 줄 소개는 AI 초안이며, 직접 작성한 문장과 사실 확인을 거친 뒤 공개합니다.</p>'
    ritual, excerpt = '리추얼 기록', '공개용 날짜별 발췌'
    stat_values = [(str(metrics['record_days']), '기록이 남은 날', ritual, excerpt),
                   (str(metrics['sessions']), '아침·마무리 리추얼', ritual, excerpt),
                   (f"{metrics['recorded_weeks']} / 13", '기록이 있는 과정 주차', ritual, '과정 시작일 기준 7일 단위'),
                   (str(metrics['recoveries_at_next_record']), '미실천 뒤 다음 기록일 재시도', ritual, '연속된 두 기록의 자기보고 상태 비교'),
                   ('미확인' if not attendance else f"{metrics['attendance']['attended']} / {len(attendance)}", '출석', '내 출석 기록', '자료 미제공' if not attendance else '제공 행 기준'),
                   ('미확인' if not tasks else f"{metrics['submissions']['submitted']} / {len(tasks)}", '과제 제출', '내 제출 현황', '자료 미제공' if not tasks else '제공 행 기준')]
    stats = ''.join(f'<div class="stat{" stat-empty" if v == "미확인" else ""}">'
                    f'<span class="stat-value">{escape(v)}</span>'
                    f'<span class="stat-label">{escape(label)}</span>'
                    f'<span class="stat-source">출처: {escape(src)}</span>'
                    f'<span class="stat-note">{escape(note)}</span></div>'
                    for v, label, src, note in stat_values)
    page = Template((ROOT / 'template.html').read_text(encoding='utf-8')).substitute(
        name=escape(profile['name']), headline=escape(profile['headline']), intro=escape(profile['intro']),
        email=escape(profile['email'], quote=True), year=profile['as_of'][:4], story=story,
        banner=draft, metrics=stats, period=escape(' ~ '.join(metrics['period']) or '기록 없음'),
        hero_pair=hero_pair(profile, metrics, statuses),
        app_due=escape('예정일: ' + profile['app_due'] if profile['app_due'] else '예정일은 13번 과제를 시작할 때 정합니다.'))
    paper = (folder / 'paper.md').read_text(encoding='utf-8-sig')
    files = {'index.html': page, 'style.css': (ROOT / 'style.css').read_text(encoding='utf-8'),
             'documents.html': document(profile, story.replace('href="#numbers"', 'href="index.html#numbers"'), draft),
             'paper.html': '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>10번 논문</title><link rel="stylesheet" href="style.css"><body><main class="document"><a href="index.html#work">← 대표작</a><h1 style="font-size:32px;letter-spacing:-1px">10번 논문</h1><pre class="paper-text">' + escape(paper) + '</pre></main></body></html>',
             'metrics.json': json.dumps(metrics, ensure_ascii=False, indent=2) + '\n'}
    if not publish:
        files['candidates.json'] = json.dumps(candidates, ensure_ascii=False, indent=2) + '\n'
    output = output.resolve()
    if output == folder.resolve() or folder.resolve().is_relative_to(output):
        raise ValueError('출력 폴더는 입력 폴더 또는 그 상위일 수 없습니다.')
    if publish and output.exists() and any(output.iterdir()):
        raise ValueError('공개 출력은 비어 있는 폴더를 사용하세요. 이전 초안 혼입을 방지합니다.')
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        if name.endswith('.html'):
            content = content.replace('<title>', '<link rel="icon" href="data:,"><title>')
        (output / name).write_text(content, encoding='utf-8', newline='\n')
    return metrics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'input')
    parser.add_argument('--output', type=Path, default=ROOT / 'preview')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    try:
        result = build(args.input, args.output, args.publish)
        print(f"OK: {args.output} ({result['record_days']} record days)")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f'Build failed: {exc}\n')
