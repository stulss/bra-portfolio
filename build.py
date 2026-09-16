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

from notion_sync import sync

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
    if not isinstance(profile.get('ability_growth'), list) or len(profile['ability_growth']) != 3:
        raise ValueError('ability_growth: 세 능력 항목이 필요합니다.')
    growth_abilities = set()
    for growth in profile['ability_growth']:
        if not isinstance(growth, dict) or growth.get('ability') not in ABILITIES:
            raise ValueError('ability_growth: 알 수 없는 능력입니다.')
        growth_abilities.add(growth['ability'])
        for key in ('before', 'practice', 'now', 'evidence'):
            text(growth[key], key)
    if growth_abilities != set(ABILITIES):
        raise ValueError('ability_growth: 세 능력을 각각 한 번씩 작성하세요.')
    for category in ('employment', 'education', 'qualifications'):
        if not isinstance(profile.get(category, []), list):
            raise ValueError(f'{category}: 배열이 필요합니다.')
        for entry in profile.get(category, []):
            if not isinstance(entry, dict):
                raise ValueError(f'{category}: 각 항목은 객체여야 합니다.')
            for key in ('period', 'organization', 'role', 'description', 'source'):
                text(entry[key], key)
            if category == 'employment':
                if not isinstance(entry.get('details'), list) or not entry['details']:
                    raise ValueError('employment.details: 비어 있지 않은 배열이 필요합니다.')
                for detail in entry['details']:
                    text(detail, '담당 업무')
    if not isinstance(profile.get('cover_letter'), list) or not profile['cover_letter']:
        raise ValueError('cover_letter: 비어 있지 않은 배열이 필요합니다.')
    for section in profile['cover_letter']:
        if not isinstance(section, dict):
            raise ValueError('cover_letter: 각 항목은 객체여야 합니다.')
        for key in ('title', 'body', 'source'):
            text(section[key], key)
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
                                   'text': f"{evidence} 이 내용을 바탕으로 {ability} 문단을 쓸 수 있습니다. 공개하기 전에는 앞뒤 맥락과 사실을 다시 확인합니다.",
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
            + (f'<span class="scene-status">{mark}</span>' if mark else '')
            + f'<span class="scene-ability">{escape(scene["ability"])}</span></div>'
            f'<div class="scene-body"><h3>{escape(scene["title"])}</h3><p>{escape(scene["body"])}</p>'
            f'<p class="source">근거: {escape(scene["source"])}</p></div></article>')


def work_style(profile: dict) -> str:
    """첫 화면에는 리추얼과 자기소개서에 함께 나온 업무 습관을 보여 준다."""
    return (
        '<div class="method-lead"><span>일이 한꺼번에 들어오면</span><strong>10초</strong></div>'
        '<ol class="method-steps"><li>먼저 멈춥니다.</li><li>처리 순서를 적습니다.</li>'
        '<li>끝난 뒤 계획과 실제를 나눠 봅니다.</li></ol>')


def markdown_inline(value: str) -> str:
    """Render the small inline Markdown subset used by the paper."""
    code: list[str] = []

    def hold(match: re.Match[str]) -> str:
        code.append(f'<code>{escape(match.group(1))}</code>')
        return f'@@CODE{len(code) - 1}@@'

    rendered = re.sub(r'`([^`]+)`', hold, value)
    rendered = escape(rendered)
    rendered = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', rendered)
    rendered = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', rendered)
    for index, snippet in enumerate(code):
        rendered = rendered.replace(f'@@CODE{index}@@', snippet)
    return rendered


def markdown_html(source: str) -> str:
    """Render headings, paragraphs, lists, quotes, tables and code without dependencies."""
    lines, output, index = source.splitlines(), [], 0
    list_pattern = re.compile(r'^\s*(?P<mark>[-+*]|\d+\.)\s+(?P<text>.+)$')
    table_rule = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$')

    def cells(line: str) -> list[str]:
        line = line.strip()
        if line.startswith('|'):
            line = line[1:]
        if line.endswith('|'):
            line = line[:-1]
        parts, part, in_code = [], [], False
        for character in line:
            if character == '`':
                in_code = not in_code
            if character == '|' and not in_code:
                parts.append(''.join(part).strip())
                part = []
            else:
                part.append(character)
        parts.append(''.join(part).strip())
        return parts

    def starts_block(line: str, next_line: str = '') -> bool:
        stripped = line.strip()
        return (not stripped or stripped.startswith(('#', '```', '>')) or
                bool(re.fullmatch(r'-{3,}', stripped)) or bool(list_pattern.match(line)) or
                ('|' in line and bool(table_rule.match(next_line))))

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith('```'):
            language = stripped[3:].strip()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith('```'):
                block.append(lines[index])
                index += 1
            index += index < len(lines)
            language_class = f' class="language-{escape(language, quote=True)}"' if language else ''
            output.append(f'<pre><code{language_class}>{escape(chr(10).join(block))}</code></pre>')
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading:
            level = len(heading.group(1))
            output.append(f'<h{level}>{markdown_inline(heading.group(2))}</h{level}>')
            index += 1
            continue
        if re.fullmatch(r'-{3,}', stripped):
            output.append('<hr>')
            index += 1
            continue
        if index + 1 < len(lines) and '|' in line and table_rule.match(lines[index + 1]):
            header = cells(line)
            index += 2
            body: list[list[str]] = []
            while index < len(lines) and '|' in lines[index] and lines[index].strip():
                body.append(cells(lines[index]))
                index += 1
            head_html = ''.join(f'<th>{markdown_inline(cell)}</th>' for cell in header)
            rows_html = ''.join('<tr>' + ''.join(f'<td>{markdown_inline(cell)}</td>' for cell in row) + '</tr>' for row in body)
            output.append(f'<div class="paper-table-scroll"><table><thead><tr>{head_html}</tr></thead><tbody>{rows_html}</tbody></table></div>')
            continue
        if stripped.startswith('>'):
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith('>'):
                quote.append(re.sub(r'^\s*>\s?', '', lines[index]))
                index += 1
            output.append(f'<blockquote>{markdown_html(chr(10).join(quote))}</blockquote>')
            continue
        item = list_pattern.match(line)
        if item:
            tag = 'ol' if item.group('mark').endswith('.') else 'ul'
            start = int(item.group('mark')[:-1]) if tag == 'ol' else 1
            items: list[str] = []
            while index < len(lines):
                current = list_pattern.match(lines[index])
                current_tag = 'ol' if current and current.group('mark').endswith('.') else 'ul'
                if not current or current_tag != tag:
                    break
                value = current.group('text')
                index += 1
                continuation: list[str] = []
                while index < len(lines) and lines[index].strip() and not list_pattern.match(lines[index]):
                    if starts_block(lines[index], lines[index + 1] if index + 1 < len(lines) else ''):
                        break
                    continuation.append(lines[index].strip())
                    index += 1
                items.append(markdown_inline(' '.join([value, *continuation])))
            start_attribute = f' start="{start}"' if tag == 'ol' and start != 1 else ''
            output.append(f'<{tag}{start_attribute}>' + ''.join(f'<li>{value}</li>' for value in items) + f'</{tag}>')
            continue
        paragraph = [stripped]
        index += 1
        while index < len(lines) and not starts_block(lines[index], lines[index + 1] if index + 1 < len(lines) else ''):
            paragraph.append(lines[index].strip())
            index += 1
        output.append(f'<p>{markdown_inline(" ".join(paragraph))}</p>')
    return ''.join(output)


def document(profile: dict) -> str:
    history = ''
    for category, heading in (('employment', '직장 경력'), ('education', '학력 및 교육'), ('qualifications', '자격사항')):
        if profile.get(category):
            history += f'<h3>{heading}</h3><ul class="resume-history">' + ''.join(
                f'<li><strong>{escape(item["period"])} · {escape(item["organization"])}</strong>'
                f'<br>{escape(item["role"])} · {escape(item["description"])}</li>'
                for item in profile[category]) + '</ul>'
    if profile.get('resume_note'):
        history += f'<p class="source">{escape(profile["resume_note"])}</p>'
    cover_letter = ''.join(
        f'<article class="cover-letter-block"><h3>{escape(section["title"])}</h3>'
        f'<p>{escape(section["body"])}</p></article>'
        for section in profile['cover_letter'])
    career_pages = ''
    for page_number, start in enumerate(range(0, len(profile['employment']), 2)):
        career_details = ''.join(
            f'<article class="career-detail"><div class="career-heading"><div><h3>{escape(item["organization"])}</h3>'
            f'<p>{escape(item["role"])}</p></div><p class="career-period">{escape(item["period"])}</p></div>'
            '<h4>주요 업무</h4><ul>' + ''.join(f'<li>{escape(detail)}</li>' for detail in item['details'])
            + '</ul></article>' for item in profile['employment'][start:start + 2])
        continuation = ' <small>계속</small>' if page_number else ''
        summary = ('<p class="career-summary">교육행정과 과정 운영, 기업·학생 관리, 현장 운영 업무를 수행했습니다.</p>'
                   if page_number == 0 else '')
        career_pages += f'<section class="career-page"><h2>경력기술서{continuation}</h2>{summary}{career_details}</section>'
    return (f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(profile["name"])} · 지원 문서</title><link rel="stylesheet" href="style.css">'
            '<body><main class="document"><p class="no-print"><a href="index.html">← 소개 사이트</a></p>'
            '<button class="print-button no-print" onclick="window.print()">인쇄 / PDF 저장</button>'
            f'<section><h1 style="font-size:40px;letter-spacing:-2px">이력서</h1><h2>{escape(profile["name"])}</h2>'
            f'<p>{escape(profile["email"])}</p><p>{escape(profile["headline"])}</p>'
            + history +
            '<h3>프로젝트 경험</h3><ul>' + ''.join(f'<li>{escape(r["period"])} · {escape(r["title"])}</li>' for r in profile['career']) +
            '</ul></section>'
            f'<section><h2>자기소개서</h2>{cover_letter}</section>{career_pages}</main></body></html>')


def build(folder: Path, output: Path, publish: bool = False) -> dict:
    profile, rows, attendance, tasks = load(folder)
    if publish:
        if not all(profile.get(k) is True for k in ('human_lines_confirmed', 'privacy_reviewed', 'facts_reviewed')):
            raise ValueError('직접 작성 문장·개인정보·사실 확인이 필요합니다.')
        if not profile['headline'].endswith('사람') or not profile.get('app_due'):
            raise ValueError('한 줄 소개 형식과 앱 예정일을 확인하세요.')
        if not profile['story'] or any(s['approved'] is not True for s in profile['story']):
            raise ValueError('본문에 미승인 장면이 있습니다.')
    metrics, candidates = aggregate(profile, rows, attendance, tasks)
    statuses = {r['date']: r['status'] for r in rows}
    story = ''.join(scene_html(s, statuses.get(s['date'])) for s in profile['story'])
    if metrics['recovery_pairs']:
        story += f'<p class="recovery">“못 했다”고 쓴 뒤 다음 기록에서 다시 해 본 경우가 {len(metrics["recovery_pairs"])}번 있습니다. <a href="#numbers">숫자로 보기</a></p>'
    ritual, excerpt = '리추얼 기록', '공개용 기록 발췌'
    stat_values = [(str(metrics['record_days']), '기록이 남은 날', ritual, excerpt),
                   (str(metrics['sessions']), '아침·마무리 리추얼', ritual, excerpt),
                   (f"{metrics['recorded_weeks']} / 13", '기록이 있는 과정 주차', ritual, '과정 시작일 기준 7일 단위'),
                   (str(metrics['recoveries_at_next_record']), '미실천 뒤 다음 기록일 재시도', ritual, '연속된 두 기록의 자기보고 상태 비교')]
    stats = ''.join('<div class="stat">'
                    f'<span class="stat-value">{escape(v)}</span>'
                    f'<span class="stat-label">{escape(label)}</span>'
                    f'<span class="stat-source">출처: {escape(src)}</span>'
                    f'<span class="stat-note">{escape(note)}</span></div>'
                    for v, label, src, note in stat_values)
    growth = ''.join(
        f'<article class="growth-row"><h3>{escape(item["ability"])}</h3>'
        f'<div><span>처음</span><p>{escape(item["before"])}</p></div>'
        f'<div><span>반복한 행동</span><p>{escape(item["practice"])}</p></div>'
        f'<div><span>지금</span><p>{escape(item["now"])}</p><small>근거: {escape(item["evidence"])}</small></div></article>'
        for item in profile['ability_growth'])
    page = Template((ROOT / 'template.html').read_text(encoding='utf-8')).substitute(
        name=escape(profile['name']), headline=escape(profile['headline']), intro=escape(profile['intro']),
        email=escape(profile['email'], quote=True), story=story, growth=growth,
        metrics=stats,
        work_style=work_style(profile),
        app_due=escape('예정일: ' + profile['app_due'] if profile['app_due'] else '예정일은 13번 과제를 시작할 때 정합니다.'))
    paper = (folder / 'paper.md').read_text(encoding='utf-8-sig')
    files = {'index.html': page, 'style.css': (ROOT / 'style.css').read_text(encoding='utf-8'),
             'documents.html': document(profile),
             'paper.html': '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>10번 논문</title><link rel="stylesheet" href="style.css"><body><main class="document paper-page"><a href="index.html#work">← 대표작</a><article class="paper">' + markdown_html(paper) + '</article></main></body></html>',
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
    parser.add_argument('--no-sync', action='store_true', help='노션 동기화 없이 현재 input으로만 생성')
    args = parser.parse_args()
    try:
        if not args.no_sync:
            print(sync(args.input))
        result = build(args.input, args.output, args.publish)
        print(f"OK: {args.output} ({result['record_days']} record days)")
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        parser.exit(1, f'Build failed: {exc}\n')
