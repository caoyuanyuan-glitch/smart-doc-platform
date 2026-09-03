"""Local Chinese cross-reference checks for nearby captions and quoted page titles."""

from __future__ import annotations

import re

_AS_SHOWN_RE = re.compile(r'如(图|表)\s*(\d+)\s*所示')
_NEAR_CAPTION_RE = re.compile(r'(图|表)\s*(\d+)\s+')
_PAGE_QUOTE_RE = re.compile(r'第\s*(\d+)\s*页\s*[“"「]\s*([^”"」]{2,40}?)\s*[”"」]')
_HEADING_LINE_RE = re.compile(r'(?m)^[ \t]*([\u4e00-\u9fffA-Za-z][^\n]{2,36})[ \t]*$')
_TOC_TITLE_RE = re.compile(r'(?m)\|\s*([^|\n]{4,40}?)\s*\|\s*(\d{1,3})\s*$')
_STOP_TOKENS = {
    '根据', '参考', '进行', '计算', '每个', '所示', '如下', '以及', '或者',
    '所测得', '所需的', '投入的', '操作', '步骤', '体积',
}


def _tokens(text: str) -> set[str]:
    tokens = set()
    for part in re.findall(r'[\u4e00-\u9fff]+|[A-Za-z]{2,}', str(text or '')):
        if re.fullmatch(r'[A-Za-z]{2,}', part):
            tokens.add(part)
            continue
        if 2 <= len(part) <= 6:
            tokens.add(part)
        for index in range(len(part) - 1):
            tokens.add(part[index:index + 2])
    return {token for token in tokens if token not in _STOP_TOKENS}


def _compact(text: str) -> str:
    return re.sub(r'\s+', '', str(text or ''))


def _is_heading_candidate(title: str) -> bool:
    compact = _compact(title)
    if not (4 <= len(compact) <= 24):
        return False
    if re.match(r'^(图|表)\s*\d+', title.strip()):
        return False
    if re.search(r'[。；;：:]$', title.strip()):
        return False
    if title.strip() in {'提示', '注意', '警告', '小心'}:
        return False
    return bool(re.search(r'[\u4e00-\u9fff]', compact))


def _page_at(page_spans, offset: int):
    for span in page_spans or []:
        if span['start'] <= offset < span['end']:
            return span.get('printed')
        if offset == span['end'] and span is page_spans[-1]:
            return span.get('printed')
    return None


def _collect_headings(normalized: str) -> list[dict]:
    headings = []
    seen = set()
    for match in _HEADING_LINE_RE.finditer(normalized):
        title = match.group(1).strip()
        if not _is_heading_candidate(title):
            continue
        key = _compact(title)
        if key in seen:
            continue
        seen.add(key)
        headings.append({'title': title, 'start': match.start(), 'compact': key})
    for match in _TOC_TITLE_RE.finditer(normalized):
        title = match.group(1).strip()
        if not _is_heading_candidate(title):
            continue
        key = _compact(title)
        if key in seen:
            continue
        seen.add(key)
        headings.append({'title': title, 'start': match.start(), 'compact': key})
    return headings


def iter_cn_local_xref_hits(raw_content, normalized, page_spans=None):
    """Yield add_issue argument tuples for nearby caption and quoted-title mismatches."""
    text = str(normalized or raw_content or '')
    if not text:
        return

    for match in _AS_SHOWN_RE.finditer(text):
        kind, cited = match.group(1), int(match.group(2))
        window = text[match.end(): match.end() + 280]
        caption = _NEAR_CAPTION_RE.search(window)
        if not caption or caption.group(1) != kind:
            continue
        actual = int(caption.group(2))
        if actual == cited:
            continue
        original = re.sub(r'\s+', ' ', match.group(0)).strip()
        yield (
            match.start(), match.end(), original,
            'CYY-CN-REF-006', '交叉引用',
            f'建议改为“如下{kind}所示”或“如{kind} {actual} 所示”',
            f'正文写“如{kind} {cited} 所示”，紧随其后的标题是“{kind} {actual}”，图表编号不一致。',
            'CYY人工审核经验基线 - 近邻图表编号核对',
            'serious', 96,
        )

    headings = _collect_headings(text)
    for match in _PAGE_QUOTE_RE.finditer(text):
        cited_page = int(match.group(1))
        cited_title = re.sub(r'\s+', ' ', match.group(2)).strip()
        cited_compact = _compact(cited_title)
        original = re.sub(r'\s+', ' ', match.group(0)).strip()
        sentence = re.split(r'[。\n]', text[match.end(): match.end() + 180], 1)[0]
        context_tokens = _tokens(sentence)
        cited_tokens = _tokens(cited_title)
        if re.match(r'^[和及与、,，]?\s*第\s*\d+\s*页', sentence.strip()):
            context_tokens = set()

        heading = next((item for item in headings if item['compact'] == cited_compact), None)
        if heading is None:
            heading_start = text.find(cited_title)
            if heading_start < 0:
                heading_start = text.find(cited_compact)
            actual_page = _page_at(page_spans, heading_start) if heading_start >= 0 else None
        else:
            actual_page = _page_at(page_spans, heading['start'])

        if actual_page is not None and actual_page != cited_page:
            yield (
                match.start(), match.end(), original,
                'CYY-CN-REF-008', '交叉引用',
                f'请将页码改为第 {actual_page} 页，或核对该标题所在页',
                f'引用“{cited_title}”指向第 {cited_page} 页，该标题实际出现在第 {actual_page} 页。',
                'CYY人工审核经验基线 - 标题页码交叉引用',
                'serious', 95,
            )

        best = None
        best_score = 0
        preceding = [item for item in headings if item['start'] < match.start()]
        current_compact = preceding[-1]['compact'] if preceding else None
        for item in headings:
            if item['compact'] == cited_compact:
                continue
            if item['compact'] == current_compact:
                continue
            score = len(context_tokens & _tokens(item['title']))
            if score > best_score:
                best = item
                best_score = score
        cited_overlap = len(context_tokens & cited_tokens)
        if best and best_score >= 2 and cited_overlap == 0 and best_score >= cited_overlap + 2:
            best_page = _page_at(page_spans, best['start'])
            if best_page:
                suggestion = f'建议改为第 {best_page} 页“{best["title"]}”'
            else:
                suggestion = f'建议改为“{best["title"]}”并核对页码'
            yield (
                match.start(), match.end(), original,
                'CYY-CN-REF-007', '交叉引用',
                suggestion,
                f'当前引用“{cited_title}”与后文主题不符，更接近章节“{best["title"]}”。',
                'CYY人工审核经验基线 - 引用目标章节核对',
                'serious', 94,
            )
