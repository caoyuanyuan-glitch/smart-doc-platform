from app.api import review as review_api
from fastapi import HTTPException
import pytest


def test_review_base_mode_strips_snippet_prefix():
    assert review_api._review_base_mode('snippet:hybrid') == 'hybrid'
    assert review_api._review_base_mode('snippet:rule') == 'rule'
    assert review_api._review_base_mode('hybrid') == 'hybrid'


def test_is_snippet_review_mode():
    assert review_api._is_snippet_review_mode('snippet:hybrid') is True
    assert review_api._is_snippet_review_mode('hybrid') is False


def test_snippet_scope_keeps_sentence_level_writing_issues():
    kept = [
        {'category': '语法', 'rule': 'GRAMMAR-001', 'source': 'rule'},
        {'category': '拼写/用词错误', 'rule': 'SPELL', 'source': 'spellcheck'},
        {'category': '术语一致性', 'rule': 'TERM-002', 'source': 'term'},
        {'category': '错别字/用词', 'rule': 'CN-TYPO-001', 'source': 'ai'},
        {'category': '单位格式', 'rule': 'CYY-CN-UNIT-001', 'source': 'rule'},
        {'category': '空格与排版', 'rule': 'DOC-SPACE-003', 'source': 'rule'},
        {'category': '商标格式', 'rule': 'DOC-TM-002', 'source': 'rule'},
        {
            'category': '格式规范',
            'rule': 'CYY-CN-FORMAT-005',
            'source': 'rule',
            'description': '同一文档中同时出现“10 μL”和“10μL”类写法，单位空格风格需要统一。',
        },
        {'category': '可读性', 'rule': 'AI', 'source': 'ai', 'description': '加入组分后未说明是否需要混匀。'},
    ]
    dropped = [
        {'category': '安全合规', 'rule': 'SAFE-001', 'source': 'rule'},
        {'category': '交叉引用', 'rule': 'XREF-001', 'source': 'rule'},
        {'category': '发布前自检', 'rule': 'CHECKLIST-COPYRIGHT-YEAR', 'source': 'rule'},
        {'category': '主题结构', 'rule': 'STRUCT-001', 'source': 'ai'},
    ]

    result = review_api._filter_snippet_scope_issues(kept + dropped)

    assert [item['rule'] for item in result] == [
        'GRAMMAR-001',
        'SPELL',
        'TERM-002',
        'CN-TYPO-001',
        'CYY-CN-UNIT-001',
        'DOC-SPACE-003',
        'DOC-TM-002',
        'CYY-CN-FORMAT-005',
        'AI',
    ]


def test_prepare_snippet_text_rejects_empty_and_oversize():
    with pytest.raises(HTTPException) as empty_exc:
        review_api._prepare_snippet_text('   ')
    assert empty_exc.value.status_code == 400

    with pytest.raises(HTTPException) as oversize_exc:
        review_api._prepare_snippet_text('字' * (review_api.SNIPPET_REVIEW_TEXT_LIMIT + 1))
    assert oversize_exc.value.status_code == 400

    assert review_api._prepare_snippet_text('  请检查这段术语。  ') == '请检查这段术语。'


def test_snippet_review_mode_accepts_rule_and_hybrid():
    assert review_api._snippet_review_mode('rule') == 'snippet:rule'
    assert review_api._snippet_review_mode('snippet:hybrid') == 'snippet:hybrid'
    with pytest.raises(HTTPException):
        review_api._snippet_review_mode('ai')


def test_snippet_route_registered_before_document_id():
    paths = [getattr(route, 'path', '') for route in review_api.router.routes]
    assert '/snippet' in paths
    assert paths.index('/snippet') < paths.index('/{document_id}')


def test_chinese_baseline_flags_core_tm():
    issues = review_api._run_chinese_human_baseline_rules('使用 Intel CoreTM 处理器。')
    assert any(item['rule'] == 'CYY-CN-TM-001' and 'CoreTM' in item['original_text'] for item in issues)


def test_engineering_audit_flags_core_tm():
    issues = review_api._run_manual_engineering_audit('Intel CoreTM processor')
    assert any(item['rule'] == 'DOC-TM-002' and 'CoreTM' in item['original_text'] for item in issues)


def test_punct_001_skips_chinese_windows():
    issues = review_api._run_english_heuristic_audit('请在 4 ℃ 条件下保存样本，并在 48 h 内完成。')
    assert not any(item.get('rule') == 'PUNCT-001' for item in issues)


def test_punct_001_flags_english_fullwidth_comma():
    issues = review_api._run_english_heuristic_audit('Store the sample at 4 C，then continue.')
    assert any(item.get('rule') == 'PUNCT-001' for item in issues)


def test_rxn_skips_numbered_kit_size():
    issues = review_api._run_chinese_human_baseline_rules('试剂盒规格为 16 RXN。')
    assert not any(item.get('rule') == 'CYY-CN-PRODUCT-003' for item in issues)


def test_rxn_flags_standalone_abbreviation():
    issues = review_api._run_chinese_human_baseline_rules('请将规格单位 RXN 改为反应。')
    assert any(item.get('rule') == 'CYY-CN-PRODUCT-003' for item in issues)


def test_cluster_merge_punctuation_issues():
    issues = [
        {'rule': 'PUNCT-001', 'category': '标点符号', 'original_text': '，', 'description': '全角逗号', 'position': '{"start":1,"end":2}'},
        {'rule': 'PUNCT-001', 'category': '标点符号', 'original_text': '，', 'description': '全角逗号', 'position': '{"start":10,"end":11}'},
    ]
    merged = review_api._cluster_merge_issues(issues)
    assert len(merged) == 1
    assert merged[0]['count'] == 2
    assert '2 处' in merged[0]['description']
    meta = review_api._decode_issue_position(merged[0]['position'])
    assert meta['count'] == 2
    assert len(meta['positions']) == 2


def test_synthesize_review_observations_from_clustered_issues():
    issues = [
        {
            'category': '标点符号',
            'severity': 'suggestion',
            'count': 8,
            'description': '全文共 8 处同类问题，分布于：第 3 章',
            'confidence': 80,
        },
        {
            'category': '术语一致性',
            'severity': 'serious',
            'count': 1,
            'description': '产品名大小写不一致',
            'confidence': 90,
        },
    ]
    observations = review_api._synthesize_review_observations(issues)
    assert observations[0]['title'] == '标点符号共 8 处'
    assert observations[0]['description'] == '全文共 8 处同类问题，分布于：第 3 章'
    assert all(item['title'] != '产品名大小写不一致' for item in observations)
    assert len(observations) == 1


def test_compact_review_observations_drops_issue_overlap_and_shortens():
    issues = [{
        'category': '术语一致性',
        'original_text': 'DNB 制备采用滚环扩增（RCA）原理',
        'description': '全文统一使用滚环扩增或 RCA',
        'suggestion': '全文统一使用“滚环扩增”或“RCA”',
    }]
    observations = [
        {
            'title': '滚环扩增缩写使用',
            'description': '文档中首次出现“滚环扩增（RCA）”，后续章节可能混用“滚环扩增”和“RCA”，建议统一。',
            'confidence': 70,
            'category': '术语一致性',
            'severity': 'general',
        },
        {
            'title': '表格 5-4 载片类型未定义',
            'description': '表 5-4 中出现的 FCL、FCS、FCU 载片类型在文档中未定义，用户无法判断其适用场景。建议补充载片类型说明或与试剂盒货号的对应关系。',
            'confidence': 75,
            'category': '信息完整性',
            'severity': 'serious',
        },
        {
            'title': '载片类型缺少说明',
            'description': 'FCL、FCS、FCU 未定义。',
            'confidence': 60,
            'category': '信息完整性',
            'severity': 'general',
        },
    ]
    compact = review_api._compact_review_observations(observations, issues)
    assert [item['title'] for item in compact] == ['表格 5-4 载片类型未定义']
    assert compact[0]['description'] == '表 5-4 中出现的 FCL、FCS、FCU 载片类型在文档中未定义，用户无法判断其适用场景。'
    assert len(compact[0]['description']) <= 80


def test_compact_review_observations_collapses_identical_title_and_description():
    issues = [{
        'original_text': '6 h',
        'description': '同一中文片段同时使用“30 天”和“6 h”，时间单位中英混用，建议统一。',
        'suggestion': '改为“6 小时”',
        'category': '格式规范',
    }]
    duplicate = '同一中文片段同时使用“30 天”和“6 h”，时间单位中英混用，建议统一。'
    compact = review_api._compact_review_observations(
        [{'title': duplicate, 'description': duplicate, 'confidence': 80, 'category': '格式规范'}],
        issues,
    )
    assert compact == []

    leftover = review_api._compact_review_observations(
        [{'title': duplicate, 'description': duplicate, 'confidence': 80, 'category': '格式规范'}],
        [],
    )
    assert len(leftover) == 1
    assert leftover[0]['title'] == duplicate.rstrip('。')
    assert leftover[0]['description'] == ''


def test_observation_merge_keeps_highest_confidence():
    review_api._review_observation_store.clear()
    review_api._record_review_observations(99, [
        {'title': '占位符过多', 'description': 'a', 'confidence': 60, 'category': '格式排版'},
        {'title': '占位符过多', 'description': 'b', 'confidence': 80, 'category': '格式排版'},
    ])
    items = review_api._take_review_observations(99)
    assert len(items) == 1
    assert items[0]['confidence'] == 80
    assert items[0]['description'] == 'b'


def test_engineering_skips_chinese_as_english_residual():
    issues = review_api._run_manual_engineering_audit('试剂准备后于 4 ℃ 保存，并在 48 h 内完成。')
    assert not any(item.get('rule') == 'ENG-CN-001' for item in issues)


def test_unit_003_skips_spaced_celsius_and_flags_missing_space():
    issues = review_api._run_chinese_human_baseline_rules('保存温度为 4 ℃，预变性 95℃。')
    unit_issues = [item for item in issues if item.get('rule') == 'CYY-CN-UNIT-003']
    originals = {item['original_text'] for item in unit_issues}
    assert '95℃' in originals
    assert not any('4 ℃' == item['original_text'] for item in unit_issues)
    assert all('°C' not in str(item.get('suggestion') or '') for item in unit_issues)


def test_chinese_snippet_flags_katakana_bullet_and_mixed_time_units():
    content = '解冻后请于 4 ℃保存，并在 7 天内用完。\n・ssDNA 文库：200 ng\n警告：不得超过 48 h。'
    issues = review_api._run_chinese_human_baseline_rules(content)
    rules = {item['rule'] for item in issues}
    assert 'CYY-CN-FORMAT-006' in rules
    assert 'CYY-CN-FORMAT-007' in rules
    fmt6 = next(item for item in issues if item['rule'] == 'CYY-CN-FORMAT-006')
    assert fmt6['original_text'] == '・'
    assert fmt6['suggestion'] == '•'


def test_format_rules_skip_table_cells():
    content = (
        '有效期为 30 天。\n'
        '读长模式 | 运行时间 | 试剂用量\n'
        '------ | ------ | ------\n'
        'SE50 | 6 h | 1.2 mL\n'
        'PE150 | ~30 h | 5.0 mL\n'
        '| ・密度 | 150~180 K/mm2 |'
    )
    issues = review_api._run_chinese_human_baseline_rules(content)
    rules = {item['rule'] for item in issues}
    assert 'CYY-CN-FORMAT-006' not in rules
    assert 'CYY-CN-FORMAT-007' not in rules


def test_ai_procedure_rewrite_is_kept_for_diagnostic():
    content = '在 PCR 管中依次加入以下组分：ssDNA 文库：200 ng'
    issues = [
        {
            'source': 'ai',
            'rule': '操作步骤完整性：加入组分后未明确说明是否需要混匀',
            'category': '可读性',
            'severity': 'general',
            'confidence': 70,
            'original_text': '在 PCR 管中依次加入以下组分：ssDNA 文库：200 ng',
            'suggestion': '建议补充各组分加入后的混匀操作说明',
            'description': '加入组分后未明确说明是否需要混匀',
        }
    ]
    kept, dropped = review_api._filter_ai_issues_without_document_evidence_with_reasons(issues, content)
    assert dropped == {}
    assert len(kept) == 1
    assert kept[0]['suggestion'].startswith('建议补充')
