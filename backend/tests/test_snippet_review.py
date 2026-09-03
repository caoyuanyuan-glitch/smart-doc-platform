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
        {'category': '逻辑完整性', 'rule': 'LOGIC-001', 'source': 'rule'},
        {'category': '数量计算', 'rule': 'SNIPPET-CALC-001', 'source': 'rule'},
    ]
    dropped = [
        {'category': '安全合规', 'rule': 'SAFE-001', 'source': 'rule'},
        {'category': '交叉引用', 'rule': 'XREF-001', 'source': 'rule'},
        {'category': '发布前自检', 'rule': 'CHECKLIST-COPYRIGHT-YEAR', 'source': 'rule'},
        {'category': '主题结构', 'rule': 'STRUCT-001', 'source': 'ai'},
        {'category': '发布前自检', 'rule': 'CHECKLIST-TRADEMARK', 'source': 'rule'},
        {'category': '页码', 'rule': 'CYY-CN-PAGE-001', 'source': 'rule'},
        {'category': '版式', 'rule': 'CYY-CN-LAYOUT-001', 'source': 'rule'},
        {'category': '修订记录', 'rule': 'DOC-REV-001', 'source': 'rule'},
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
        'LOGIC-001',
        'SNIPPET-CALC-001',
    ]
    assert 'CHECKLIST-TRADEMARK' not in {item['rule'] for item in result}
    assert 'CYY-CN-PAGE-001' not in {item['rule'] for item in result}
    assert 'DOC-REV-001' not in {item['rule'] for item in result}


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


def test_finalize_snippet_keeps_unit_spacing_rule():
    content = '将上述体系混匀后，37℃孵育 30 min。'
    issues = review_api._run_chinese_human_baseline_rules(content)
    assert any(item['rule'] == 'CYY-CN-UNIT-003' for item in issues)
    kept, diagnostics = review_api._finalize_review_issues(issues, content, set(), snippet_review=True)
    assert any(item['rule'] == 'CYY-CN-UNIT-003' for item in kept)
    assert diagnostics['filter_mode'] == 'snippet'


def test_finalize_full_doc_still_drops_unit_spacing_as_noise():
    content = '将上述体系混匀后，37℃孵育 30 min。'
    issues = review_api._run_chinese_human_baseline_rules(content)
    kept, diagnostics = review_api._finalize_review_issues(issues, content, set())
    assert diagnostics['filter_mode'] == 'pipeline'
    assert not any(item['rule'] == 'CYY-CN-UNIT-003' for item in kept)


def test_snippet_basis_keeps_scope_and_style():
    sections = [
        {'label': '文本片段审核范围', 'text': '【文本片段审核范围】\n只检查语法拼写术语', 'basis_type': 'snippet_scope', 'priority': 6},
        {'label': '中文技术文档写作风格指南', 'text': '【中文技术文档写作风格指南】\n数字与单位之间保留空格', 'basis_type': 'style_guide', 'priority': 4},
        {'label': '技术文档常见错误清单', 'text': '【技术文档常见错误清单】\n错别字必须报告', 'basis_type': 'common_errors', 'priority': 3},
        {'label': 'CYY人工审核经验基线-表格/版式', 'text': '【CYY人工审核经验基线-表格/版式】\n调整列宽', 'basis_type': 'cyy', 'priority': 2},
    ]
    selected = review_api._select_snippet_ai_review_basis('取出 D NB Buffer 后 37℃孵育。', sections, document_language='cn')
    assert '文本片段审核范围' in selected
    assert '中文技术文档写作风格指南' in selected
    assert '技术文档常见错误清单' in selected
    assert '表格/版式' not in selected


def test_snippet_prompt_asks_for_sentence_level_typos():
    from app.utils.ai_client import ai_client
    payload = ai_client.build_audit_prompt_payload(
        '需将样本管离新，37℃孵育。',
        language='cn',
        audit_basis='【文本片段审核范围】',
        snippet_review=True,
    )
    blob = payload['system_prompt'] + payload['user_prompt']
    assert '文本片段校对' in blob
    assert '不按普通语法校对' not in blob
    assert '错别字' in blob
    assert '总体积' in blob
    assert '步骤编号' in blob


PLANTED_SNIPPET = """DNB制备操作流程（测试文本）
准备工作
取出试剂盒中的 D NB Buffer 和 D NB Enzyme，室温放置 30 min 使其平衡至室温。
需将样本管离新（1,000 × g，1 min），收集沉淀。
配制反应体系按以下比例配制反应液（总体积 100 μL）：
Buffer 60 uL
Primer 30 μL
Enzyme 20 μL
3. 将上述体系混匀后，37℃孵育 30 min。
2. 加入 Enzyme。
本反应在 15 min 内即可完成，无需过度孵育。
产物保存
反应结束后，立即将产物置于 -20 ℃ 保存。
注意：D NB Enzyme 需严格于 -20 ℃ 保存，不可反复冻融超过 5 次。
上机前准备
每孔加入 25 μL 反应液，共进行 16 个反应。
提前准备 500 μL 反应液，确保用量充足。
"""


def test_snippet_content_audit_covers_planted_error_types():
    issues = review_api._run_snippet_content_audit(PLANTED_SNIPPET)
    rules = {item['rule'] for item in issues}
    assert 'SNIPPET-TYPO-001' in rules
    assert 'SNIPPET-SPACE-001' in rules
    assert 'SNIPPET-UNIT-001' in rules
    assert 'SNIPPET-CALC-001' in rules
    assert 'SNIPPET-TIME-001' in rules
    assert 'SNIPPET-STORE-001' in rules
    assert 'SNIPPET-CALC-002' in rules
    assert 'SNIPPET-STEP-001' in rules


def test_finalize_snippet_keeps_planted_content_rules():
    baseline = review_api._run_chinese_human_baseline_rules(PLANTED_SNIPPET)
    snippet_issues = review_api._run_snippet_content_audit(PLANTED_SNIPPET)
    kept, diagnostics = review_api._finalize_review_issues(
        baseline + snippet_issues, PLANTED_SNIPPET, set(), snippet_review=True,
    )
    rules = {item['rule'] for item in kept}
    assert diagnostics['filter_mode'] == 'snippet'
    assert 'CYY-CN-SPELL-008' in rules
    assert 'SNIPPET-SPACE-001' in rules
    assert 'SNIPPET-CALC-001' in rules
    assert 'SNIPPET-TIME-001' in rules
    assert 'SNIPPET-CALC-002' in rules


def test_run_chinese_human_baseline_rules_detects_vortex_typo():
    issues = review_api._run_chinese_human_baseline_rules(
        '盖上管盖，涡漩振荡 5 秒。',
    )
    issue = next(item for item in issues if item['rule'] == 'CYY-CN-SPELL-009')
    assert issue['original_text'] == '涡漩'
    assert '涡旋' in issue['suggestion']


def test_run_chinese_human_baseline_rules_detects_integra_brand_typo():
    issues = review_api._run_chinese_human_baseline_rules(
        '使用 Intergra 移液器转移上清。',
    )
    issue = next(item for item in issues if item['rule'] == 'CYY-CN-SPELL-010')
    assert issue['original_text'] == 'Intergra'
    assert 'Integra' in issue['suggestion']


def test_run_chinese_human_baseline_rules_detects_incomplete_avoid_phrase():
    issues = review_api._run_chinese_human_baseline_rules(
        '如操作不当或不避免交叉污染，可能导致检测失败。',
    )
    issue = next(item for item in issues if item['rule'] == 'CYY-CN-GRAMMAR-014')
    assert issue['original_text'] == '或不避免'
    assert '无法避免' in issue['suggestion'] or '以避免' in issue['suggestion']


def test_run_snippet_content_audit_detects_vortex_and_integra_typos():
    issues = review_api._run_snippet_content_audit(
        '盖上管盖，涡漩振荡 5 秒后用 Intergra 移液器转移。',
    )
    originals = {item['original_text'] for item in issues if item['rule'] == 'SNIPPET-TYPO-001'}
    assert '涡漩' in originals
    assert 'Intergra' in originals


def test_run_chinese_human_baseline_rules_detects_nearby_table_number_mismatch():
    issues = review_api._run_chinese_human_baseline_rules(
        '准确率检测结果如表 9 所示：\n表 92 “基因测序仪准确率企业参考品”检测结果\n',
    )
    issue = next(item for item in issues if item['rule'] == 'CYY-CN-REF-006')
    assert '表 9' in issue['original_text']
    assert '表 92' in issue['suggestion'] or '如下表' in issue['suggestion']


def test_run_chinese_human_baseline_rules_keeps_following_table_phrase():
    issues = review_api._run_chinese_human_baseline_rules(
        '准确率检测结果如下表所示：\n表 92 “基因测序仪准确率企业参考品”检测结果\n',
    )
    assert not any(item['rule'] == 'CYY-CN-REF-006' for item in issues)


def test_run_chinese_human_baseline_rules_detects_wrong_quoted_section_target():
    content = (
        '计算 ssDNA 文库所需量\n'
        '根据第75页“标签序列选择”所测得的 ssDNA 文库的浓度及所需的文库 fmol 量，'
        '计算每个 DNB 制备体系所需投入的 ssDNA 文库体积。\n'
        '文库浓度及所需量的要求\n'
        '标签序列选择\n'
    )
    issues = review_api._run_chinese_human_baseline_rules(content)
    issue = next(item for item in issues if item['rule'] == 'CYY-CN-REF-007')
    assert '标签序列选择' in issue['original_text']
    assert '文库浓度及所需量的要求' in issue['suggestion']


def test_run_chinese_human_baseline_rules_keeps_paired_page_title_refs():
    issues = review_api._run_chinese_human_baseline_rules(
        '标签序列和高级设置参考第 75 页“标签序列选择”和第 75 页“高级选项设置”。\n'
        '标签序列选择\n'
        '高级设置\n',
    )
    assert not any(item['rule'] == 'CYY-CN-REF-007' for item in issues)
