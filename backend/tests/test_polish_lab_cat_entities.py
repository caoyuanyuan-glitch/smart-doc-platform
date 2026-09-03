import sys
import unittest
from pathlib import Path
import json
import os
import tempfile
import time
from types import SimpleNamespace


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.polish_lab import (  # noqa: E402
    _apply_cat_entity_change_penalty,
    _backfill_critical_entities,
    _compose_cat_candidate_text,
    _critical_entity_changes,
    _filter_cat_artifact_diagnose_items,
    _filter_cat_artifact_diagnose_pool,
    _filter_cat_artifact_diagnoses,
    _get_cat_analyze_cache,
    _has_missing_icon_button_name,
    _is_dropped_cat_artifact_revision,
    _is_trivial_cat_artifact_edit,
    _reapply_sentence_prefix,
    _simple_match,
    _split_cat_sentences,
    _split_step_prefix,
    _store_cat_analyze_cache,
    replace_with_context,
)

import app.api.polish_lab as polish_lab  # noqa: E402


class PolishLabCatEntityTest(unittest.TestCase):
    def test_split_cat_sentences_strips_leftover_step_dot(self):
        items = _split_cat_sentences(
            ['3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'],
            source_paragraphs=['3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'],
        )
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]['text'].startswith('点击'))
        self.assertFalse(items[0]['text'].startswith('.'))

    def test_reapply_prefix_collapses_double_dots(self):
        original = '3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'
        composed = _compose_cat_candidate_text(original, '.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。')
        self.assertNotIn('3.2.1..', composed)
        self.assertTrue(composed.startswith('3.2.1.点击'))
        prefix, body = _split_step_prefix('3.2.1..点击测试按钮，进入界面。')
        self.assertEqual(prefix, '3.2.1.')
        self.assertTrue(body.startswith('点击'))
        collapsed = _reapply_sentence_prefix(original, '.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。')
        self.assertNotIn('..', collapsed)

    def test_compose_keeps_complete_email_domain(self):
        source = '若您有其他疑问，请联系MGI技术支持：MGI-service@genomics.cn'
        template = '若有其他疑问，请联系技术支持：MGI-service@mgi-tech.com。'
        composed = _compose_cat_candidate_text(source, template)
        self.assertNotIn('comics.cn', composed)
        self.assertIn('mgi-tech.com', composed)

    def test_semicolon_mix_step_is_not_spliced_onto_complete_sentence(self):
        source = '解冻后用漩涡混匀仪充分混匀，瞬时离心后置于冰上待用。'
        template = '使用涡旋振荡器振荡混匀5秒并短暂离心后置于冰盒上备用；'
        composed = _compose_cat_candidate_text(source, template)
        self.assertNotIn('漩涡混匀仪充分混匀，使用涡旋振荡器', composed)
        self.assertNotIn('；。', composed)
        hits = _simple_match(source, [{'text': template, 'id': 't'}], source_sentence=source)
        self.assertFalse(any('涡旋振荡器' in str(item.get('template_text') or '') for item in hits))
        long_template = (
            'DNB加载体系配制步骤如下：取出DNB加载缓冲液II置于冰上约30分钟融化；'
            '使用涡旋振荡器振荡混匀5秒并短暂离心后置于冰盒上备用；'
            '若DNB加载缓冲液II中有结晶，使用涡旋振荡器振荡至沉淀重新溶解。'
        )
        long_hits = _simple_match(source, [{'text': long_template, 'id': 'l'}], source_sentence=source)
        self.assertFalse(any('涡旋振荡器' in str(item.get('template_text') or '') for item in long_hits))

    def test_compose_keeps_spaced_model_suffix(self):
        source = 'DNBelab-D4 RS RNA文库制备试剂盒套装由3个独立盒子包装。'
        joined = 'DNBelab-D4RS RNA文库制备试剂盒套装由3个独立盒子包装。'
        composed = _compose_cat_candidate_text(source, joined)
        self.assertIn('DNBelab-D4RS', composed)
        self.assertNotIn('DNBelab-D4 RNA', composed)
        hits = [item for item in _simple_match(source, [], source_sentence=source) if item.get('rule_source') == 'surface_rules']
        self.assertTrue(hits)
        self.assertIn('DNBelab-D4RS', hits[0]['template_text'])
        self.assertNotIn('DNBelab-D4 RNA', hits[0]['template_text'])

    def test_compose_keeps_pooling_purpose_clause_and_chinese_count(self):
        source = '且一张制备卡四个样本的投入量建议相同或相近，这样可以保证四个样本出库浓度相对一致，便于后续pooling测序。'
        template = '每张样本制备卡四个样本的投入量建议相同或相近，以保证4个样本出库浓度相对一致。'
        composed = _compose_cat_candidate_text(source, template)
        self.assertIn('便于后续pooling测序', composed)
        self.assertIn('四个样本出库浓度', composed)
        self.assertNotIn('4个样本出库浓度', composed)
        self.assertIn('一张制备卡', composed)
        hits = _simple_match(source, [{'text': template, 'id': 't'}], source_sentence=source)
        self.assertTrue(hits)
        self.assertIn('便于后续pooling测序', hits[0]['template_text'])
        self.assertIn('四个样本出库浓度', hits[0]['template_text'])

    def test_compose_does_not_duplicate_similar_pooling_clause(self):
        source = '搭配MGISEQ-2000测序时建议每个样品DNB投入量6.25μL，DNB加载体系参考MGISEQ-2000RS高通量（快速）测序试剂套装使用说明书。'
        candidate = '搭配MGISEQ-2000测序时建议每个样本DNB投入量6.25 μL，DNB加载体系参考MGISEQ-2000RS高通量（快速）测序试剂套装使用说明书。'
        composed = _compose_cat_candidate_text(source, candidate)
        self.assertEqual(composed.count('搭配MGISEQ-2000测序时'), 1)

    def test_platform_entity_change_is_penalized_not_dropped(self):
        source = '搭配MGISEQ-2000测序时建议每个样品DNB投入量6.25μL，DNB加载体系参考MGISEQ-2000RS高通量（快速）测序试剂套装使用说明书。'
        dirty = '搭配MGISEQ-2000测序时建议每个样品DNB投入量6.25μL，DNB加载体系的配制参考MGISEQ-200RS高通量（快速）测序试剂套装使用说明书。'
        changes = _critical_entity_changes(source, dirty)
        self.assertTrue(any('测序平台' in item or '试剂套装名' in item for item in changes))
        candidates = _simple_match(
            source,
            [{'text': dirty, 'id': 't1'}],
            min_threshold=0.34,
            source_sentence=source,
        )
        guide_hits = [item for item in candidates if item.get('rule_source') == 'sentence_guide']
        self.assertTrue(guide_hits)
        self.assertNotIn('entity_changed', guide_hits[0].get('review_tags') or [])
        self.assertIn('的配制', guide_hits[0]['template_text'])
        self.assertIn('MGISEQ-2000RS', guide_hits[0]['template_text'])
        self.assertNotIn('MGISEQ-200RS高通量', guide_hits[0]['template_text'])
        penalized = _apply_cat_entity_change_penalty(source, {
            'template_text': dirty,
            'string_score': 0.834,
        })
        self.assertLess(penalized['string_score'], 0.834)
        self.assertGreaterEqual(penalized['string_score'], 0.50)

    def test_leading_dot_and_de_only_are_not_recalled(self):
        dotted = '.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'
        cleaned = '点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'
        self.assertTrue(_is_trivial_cat_artifact_edit(dotted, cleaned))
        dotted_hits = _simple_match(dotted, [], source_sentence=dotted)
        self.assertFalse(dotted_hits)
        source = '可以根据试剂盒中试剂管盖颜色来确定该试剂加载区域。'
        only_de = '可以根据试剂盒中试剂管盖的颜色来确定该试剂加载区域。'
        self.assertTrue(_is_trivial_cat_artifact_edit(source, only_de))
        de_hits = [item for item in _simple_match(source, [{'text': only_de, 'id': 't'}], source_sentence=source) if item.get('rule_source') == 'sentence_guide']
        self.assertFalse(de_hits)

    def test_missing_icon_button_spacing_is_trivial(self):
        source = '点击DNBelab-D4RS制备系统界面上 按钮，进入试剂盒信息录入界面（图3）。'
        candidate = '点击DNBelab-D4RS制备系统界面上按钮，进入试剂盒信息录入界面（图3）。'
        self.assertTrue(_is_trivial_cat_artifact_edit(source, candidate))

    def test_coordinated_claim_suffix_is_not_trimmed_as_duplicate(self):
        source = (
            '本试剂盒利用数字微流控技术结合了DNBelab-D4RS平台使得RNA建库实现完全自动化，'
            '同时采用高质量的酶学组成，改进型接头连接技术以及具有强扩增效率的高保真酶，'
            '显著提高文库转化率与扩增效率；'
        )
        self.assertIn('与扩增效率', polish_lab._trim_redundant_cat_suffix(source))
        self.assertEqual(
            polish_lab._trim_redundant_cat_suffix('显著提高文库转化率与转化率。'),
            '显著提高文库转化率。',
        )
        composed = _compose_cat_candidate_text(source, source)
        self.assertIn('与扩增效率', composed)
        hits = _simple_match(source, [], source_sentence=source)
        self.assertFalse(any('显著提高文库转化率；' in str(item.get('template_text') or '') for item in hits))
        self.assertFalse(any(
            '与扩增效率' not in str(item.get('template_text') or '')
            for item in hits
        ))


    def test_list_intro_does_not_splice_platform_template(self):
        source = '构建的文库可使用以下平台及测序类型测序：'
        library = '构建的文库推荐使用DNBSEQ-G99RS(SE100/PE150)测序。'
        listing = '构建的文库推荐使用以下平台及测序类型测序：MGISEQ-200RS(SE50/SE100/PE150)。'
        composed = _compose_cat_candidate_text(source, library)
        self.assertNotIn('测序类型测序', composed)
        self.assertFalse(composed.endswith('测序类型测序：'))
        self.assertTrue(
            polish_lab._has_conflicting_list_intro(source, library)
        )
        self.assertFalse(
            polish_lab._has_conflicting_list_intro(source, listing)
        )
        hits = _simple_match(
            source,
            [{'text': library, 'id': 't1'}, {'text': listing, 'id': 't2'}],
            source_sentence=source,
        )
        texts = [str(item.get('template_text') or '') for item in hits]
        self.assertFalse(any('DNBSEQ-G99RS' in item and '测序类型测序' in item for item in texts))
        self.assertFalse(any(item == '构建的文库推荐使用DNBSEQ-G99RS(SE100/PE150)测序类型测序：' for item in texts))

    def test_diagnose_skips_missing_icon_and_de_only(self):
        original = '3.2.1. 点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'
        only_de = '3.2.1. 点击DNBelab-D4RS制备系统界面上的按钮，进入样本制备卡信息录入界面（图2）。'
        named = '点击界面上「开始」按钮，进入样本制备卡信息录入界面（图2）。'
        self.assertTrue(_has_missing_icon_button_name(original))
        self.assertTrue(_is_dropped_cat_artifact_revision(original, only_de))
        self.assertFalse(_has_missing_icon_button_name(named))
        pool = _filter_cat_artifact_diagnose_pool([
            {'sentence_index': 25, 'text': original, 'source_sentence_text': original},
            {'sentence_index': 26, 'text': named, 'source_sentence_text': named},
        ])
        self.assertEqual([item['sentence_index'] for item in pool], [26])
        diags = _filter_cat_artifact_diagnoses(
            [
                {'sentence_index': 25, 'quote': original, 'revised': only_de, 'category': 'word'},
                {'sentence_index': 26, 'quote': named, 'revised': named.replace('开始', '下一步'), 'category': 'word'},
            ],
            [
                {'sentence_index': 25, 'source_sentence_text': original},
                {'sentence_index': 26, 'source_sentence_text': named},
            ],
        )
        self.assertEqual([item['sentence_index'] for item in diags], [26])
        items = _filter_cat_artifact_diagnose_items([
            {
                'original_text': original,
                'candidates': [{'template_text': only_de, 'category': 'word'}],
            },
            {
                'original_text': '可以根据试剂盒中试剂管盖颜色来确定该试剂加载区域。',
                'candidates': [{'template_text': '可以根据试剂盒中试剂管盖的颜色来确定该试剂加载区域。', 'category': 'word'}],
            },
        ])
        self.assertFalse(items)

    def test_entity_backfill_keeps_preparation_diff(self):
        source = '6. 四样本混样时，搭配DNBSEQ-G99测序时建议每个样品DNB投入量5.25μL，DNB加载体系参考DNBSEQ-G99RS高通量测序试剂套装使用说明书；'
        dirty = 'DNB加载体系的配制参考MGISEQ-200RS高通量(快速)测序试剂套装使用说明书。'
        filled = _backfill_critical_entities(source, _compose_cat_candidate_text(source, dirty))
        self.assertIn('的配制', filled)
        self.assertIn('DNBSEQ-G99RS', filled)
        self.assertNotIn('MGISEQ-200RS', filled)
        self.assertFalse(_critical_entity_changes(source, filled))

    def test_replace_with_context_does_not_concat_appendix(self):
        source = '试剂加载区（A,B,C）的颜色和该区域对应加载的试剂的管盖的颜色一致，可以根据试剂盒中试剂管盖颜色来确定该试剂加载区域。'
        template = '试剂加载区的颜色应与该区域对应加载的试剂的管盖颜色一致，可以根据管盖颜色来确定对应的试剂加载区域。产物混样、上机前的DNB加载及测序建议，参考第23页"产物pooling及测序方案"。'
        merged = replace_with_context(source, template)
        self.assertFalse('试剂加载区（A,B,C）' in merged and '参考第23页' in merged)
        composed = _compose_cat_candidate_text(
            '3.' + source,
            '产物混样、上机前的DNB加载及测序建议，参考第23页"产物pooling及测序方案"。',
        )
        self.assertFalse('试剂加载区' in composed and '参考第23页' in composed)
        hits = _simple_match(
            '3.' + source,
            [{'text': '产物混样、上机前的DNB加载及测序建议，参考第23页"产物pooling及测序方案"。', 'id': 't'}],
            source_sentence='3.' + source,
        )
        self.assertFalse(any('参考第23页' in str(item.get('template_text') or '') for item in hits))

    def test_markdown_escaped_email_domain_is_unescaped(self):
        table = (
            '|序号|句式模板|示例|\n'
            '|---|---|---|\n'
            '|1|若有其他疑问，请联系...|"若有其他疑问，请联系技术支持：MGI\\-service@mgi\\-tech\\.com。"|\n'
        )
        sentences = polish_lab._parse_table_sentence_templates(table)
        self.assertEqual(len(sentences), 1)
        self.assertIn('MGI-service@mgi-tech.com', sentences[0])
        self.assertNotIn('\\.', sentences[0])
        source = '若您有其他疑问，请联系MGI技术支持：MGI-service@genomics.cn。'
        composed = _compose_cat_candidate_text(source, sentences[0])
        self.assertIn('mgi-tech.com', composed)
        self.assertNotIn('\\', composed)
        escaped = '若有其他疑问，请联系技术支持：MGI-service@mgi-tech\\.com。'
        composed_escaped = _compose_cat_candidate_text(source, escaped)
        self.assertIn('mgi-tech.com', composed_escaped)
        self.assertNotIn('\\.', composed_escaped)

    def test_compose_keeps_parenthetical_reagent_code(self):
        source = '实验前需提前将冷藏试剂中的磁珠（A567-RNA-BE）室温平衡半个小时。'
        template = '实验前需提前将冷藏试剂中的磁珠室温平衡半个小时。'
        composed = _compose_cat_candidate_text(source, template)
        self.assertIn('A567-RNA-BE', composed)
        hits = _simple_match(source, [{'text': template, 'id': 't'}], source_sentence=source)
        self.assertFalse(any(
            '磁珠室温平衡' in str(item.get('template_text') or '')
            and 'A567-RNA-BE' not in str(item.get('template_text') or '')
            for item in hits
        ))

    def test_injected_ui_bracket_label_is_not_recalled(self):
        source = '3.4.2根据自己测序需求，在下拉框中选择相对应的测序平台'
        template = '在测序平台选择界面，点击【适配测序平台】下拉箭头，并在弹出的列表中选择适配的测序平台。'
        self.assertTrue(polish_lab._has_injected_ui_bracket_labels(source, template))
        hits = _simple_match(source, [{'text': template, 'id': 't'}], source_sentence=source)
        self.assertFalse(any('【适配测序平台】' in str(item.get('template_text') or '') for item in hits))

    def test_manual_vs_auto_operation_mode_is_not_recalled(self):
        source = '完成后，按界面提示手动关上仓门。'
        template = '制备卡仓门自动打开，载台自动推出。'
        ok, reason = polish_lab._key_term_anchor_consistent(source, template)
        self.assertFalse(ok)
        self.assertIn('operation_mode', reason)
        hits = _simple_match(source, [{'text': template, 'id': 't'}], source_sentence=source)
        self.assertFalse(any('仓门自动打开' in str(item.get('template_text') or '') for item in hits))


class PolishLabCatAnalyzeCacheTest(unittest.TestCase):
    def setUp(self):
        self._orig_dir = polish_lab._CAT_ANALYZE_CACHE_DIR
        self._orig_ttl = polish_lab._CAT_CACHE_TTL_SECONDS
        self._tmpdir = tempfile.TemporaryDirectory()
        polish_lab._CAT_ANALYZE_CACHE_DIR = self._tmpdir.name
        polish_lab._cat_analyze_cache.clear()
        polish_lab._cat_cache_timestamps.clear()

    def tearDown(self):
        polish_lab._CAT_ANALYZE_CACHE_DIR = self._orig_dir
        polish_lab._CAT_CACHE_TTL_SECONDS = self._orig_ttl
        polish_lab._cat_analyze_cache.clear()
        polish_lab._cat_cache_timestamps.clear()
        self._tmpdir.cleanup()

    def test_get_restores_after_memory_loss(self):
        source = os.path.join(self._tmpdir.name, "src.docx")
        with open(source, "w", encoding="utf-8") as f:
            f.write("dummy")
        analyze_id = "cache-restore-1"
        _store_cat_analyze_cache(analyze_id, {
            "items": [{"original_text": "hello", "has_candidates": True}],
            "templates": [],
            "file_info": {"filename": "src.docx", "temp_path": source},
        })
        polish_lab._cat_analyze_cache.clear()
        polish_lab._cat_cache_timestamps.clear()
        loaded = _get_cat_analyze_cache(analyze_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["items"][0]["original_text"], "hello")
        self.assertTrue(os.path.isfile(loaded["file_info"]["temp_path"]))

    def test_get_falls_back_to_persisted_source(self):
        source = os.path.join(self._tmpdir.name, "src.docx")
        with open(source, "w", encoding="utf-8") as f:
            f.write("dummy")
        analyze_id = "cache-source-1"
        _store_cat_analyze_cache(analyze_id, {
            "items": [{"original_text": "hello"}],
            "templates": [],
            "file_info": {"filename": "src.docx", "temp_path": source},
        })
        moved = source + ".moved"
        os.replace(source, moved)
        polish_lab._cat_analyze_cache.clear()
        polish_lab._cat_cache_timestamps.clear()
        loaded = _get_cat_analyze_cache(analyze_id)
        self.assertIsNotNone(loaded)
        restored = loaded["file_info"]["temp_path"]
        self.assertNotEqual(restored, source)
        self.assertTrue(os.path.isfile(restored))

    def test_expired_disk_cache_is_ignored(self):
        analyze_id = "cache-expired-1"
        _store_cat_analyze_cache(analyze_id, {
            "items": [],
            "templates": [],
            "file_info": {"filename": "src.docx"},
        })
        json_path = polish_lab._cat_analyze_cache_json_path(analyze_id)
        with open(json_path, encoding="utf-8") as f:
            blob = json.load(f)
        blob["saved_at"] = time.time() - polish_lab._CAT_CACHE_TTL_SECONDS - 10
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(blob, f)
        polish_lab._cat_analyze_cache.clear()
        polish_lab._cat_cache_timestamps.clear()
        self.assertIsNone(_get_cat_analyze_cache(analyze_id))


class PolishLabCatReportTest(unittest.TestCase):
    def test_issue_meta_uses_page_category_and_severity(self):
        decision = SimpleNamespace(
            action='accept',
            paragraph_index=0,
            sentence_index=1,
            source_paragraph_index=0,
            original_text='点击按钮进入界面。',
            accepted_template='点击按钮，进入界面。',
            category='grammar',
            severity='high',
            candidate_text='点击按钮，进入界面。',
            rule_source='ai_diagnose',
        )
        meta = polish_lab._cat_report_issue_meta(decision)
        self.assertEqual(meta['category_label'], '语法')
        self.assertEqual(meta['severity_label'], '高 · 严重问题')
        self.assertEqual(meta['original_text'], '点击按钮进入界面。')
        self.assertEqual(meta['candidate_text'], '点击按钮，进入界面。')
        self.assertEqual(meta['final_text'], '点击按钮，进入界面。')

    def test_issue_meta_falls_back_to_cached_candidate(self):
        decision = SimpleNamespace(
            action='pending',
            paragraph_index=2,
            sentence_index=3,
            source_paragraph_index=2,
            original_text='样本保存于室温。',
            accepted_template='',
            rejected_template='',
            modified_text='',
            category='',
            severity='',
            candidate_text='',
        )
        cached_items = [{
            'source_paragraph_index': 2,
            'sentence_index': 3,
            'original_text': '样本保存于室温。',
            'candidates': [{
                'category': 'risk',
                'severity': 'medium',
                'template_text': '样本应保存于2℃至8℃。',
                'revised': '样本应保存于2℃至8℃。',
                'rule_source': 'ai_diagnose',
            }],
        }]
        meta = polish_lab._cat_report_issue_meta(decision, cached_items)
        self.assertEqual(meta['category_label'], '风险')
        self.assertEqual(meta['severity_label'], '中 · 建议关注')
        self.assertEqual(meta['candidate_text'], '样本应保存于2℃至8℃。')
        self.assertEqual(meta['final_text'], '')

    def test_html_report_groups_by_issue_category(self):
        decision = SimpleNamespace(
            action='accept',
            paragraph_index=0,
            sentence_index=0,
            source_paragraph_index=0,
            original_text='点击按钮进入界面。',
            accepted_template='点击按钮，进入界面。',
            category='word',
            severity='low',
            candidate_text='点击按钮，进入界面。',
            rule_source='ai_diagnose',
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = os.path.join(tmpdir, 'report.html')
            polish_lab._generate_cat_html_report(
                report_path=report_path,
                source_filename='demo.docx',
                analyze_id='aid-1',
                decisions=[decision],
                applied_changes=[],
                accuracy={'accuracy_rate': None},
                failed_replacements=[],
                ai_semantic_scoring=True,
            )
            with open(report_path, encoding='utf-8') as f:
                html = f.read()
        self.assertIn('问题类别', html)
        self.assertIn('AI诊断严重程度分类', html)
        self.assertIn('用词', html)
        self.assertIn('低 · 提示性', html)
        self.assertIn('候选', html)
        self.assertIn('最终文本', html)
        self.assertIn('AI语义', html)
        self.assertIn('已开启', html)
        self.assertNotIn('表达精简', html)
        self.assertNotIn('变化摘要', html)
        self.assertIn('diff-remove', html)
        self.assertIn('diff-add', html)

    def test_unprocessed_final_text_is_empty(self):
        decision = SimpleNamespace(
            action='reject',
            paragraph_index=0,
            sentence_index=0,
            source_paragraph_index=0,
            original_text='样本保存于室温。',
            rejected_template='样本应保存于2℃至8℃。',
            category='risk',
            severity='high',
            candidate_text='样本应保存于2℃至8℃。',
        )
        meta = polish_lab._cat_report_issue_meta(decision)
        self.assertEqual(meta['final_text'], '')
        original_html, candidate_html = polish_lab._cat_report_render_compare_html(
            meta['original_text'],
            meta['candidate_text'],
        )
        self.assertIn('diff-remove', original_html)
        self.assertIn('diff-add', candidate_html)

    def test_non_ai_diagnose_severity_is_slash(self):
        decision = SimpleNamespace(
            action='accept',
            paragraph_index=0,
            sentence_index=0,
            source_paragraph_index=0,
            original_text='点击按钮进入界面。',
            accepted_template='点击按钮，进入界面。',
            category='grammar',
            severity='high',
            candidate_text='点击按钮，进入界面。',
            rule_source='sentence_guide',
        )
        meta = polish_lab._cat_report_issue_meta(decision)
        self.assertEqual(meta['severity_label'], '/')
        self.assertFalse(meta['is_ai_diagnose'])


class PolishLabCatCategoryG1Test(unittest.TestCase):
    def test_punctuation_maps_to_grammar(self):
        self.assertEqual(
            polish_lab._cat_report_change_category('点击按钮进入界面。', '点击按钮，进入界面。', 'modify'),
            'grammar',
        )

    def test_typo_maps_to_word(self):
        self.assertEqual(
            polish_lab._cat_report_change_category(
                '实验前将所有的冷冻试剂至于常温解冻。',
                '实验前将所有的冷冻试剂置于常温解冻。',
                'modify',
            ),
            'word',
        )

    def test_term_unification_maps_to_term(self):
        self.assertEqual(
            polish_lab._cat_report_change_category(
                '将制备卡平置于机器上。',
                '将制备卡平置于仪器上。',
                'modify',
            ),
            'term',
        )

    def test_reorder_maps_to_logic(self):
        self.assertEqual(
            polish_lab._cat_report_change_category('先离心，再混匀。', '先混匀，再离心。', 'modify'),
            'logic',
        )

    def test_shorten_maps_to_redundancy(self):
        self.assertEqual(
            polish_lab._cat_report_change_category(
                '本说明书中的所有图片均为示意图，图片内容可能与实物有细微差异，请以购买的产品为准。',
                '图片为示意图。',
                'modify',
            ),
            'redundancy',
        )

    def test_lengthen_maps_to_missing(self):
        self.assertEqual(
            polish_lab._cat_report_change_category(
                '混匀后瞬时离心。',
                '混匀后瞬时离心，便于后续pooling测序。',
                'modify',
            ),
            'missing',
        )

    def test_imperative_wording_maps_to_term(self):
        self.assertEqual(
            polish_lab._cat_report_change_category('点击开始按钮。', '请点击开始按钮。', 'modify'),
            'term',
        )

    def test_simple_match_guide_candidate_has_eight_class_category(self):
        source = '3.8.4将制备卡平置于机器上，制备卡的凹口要与机器推板上的凸出位置对应（图12）。'
        template = '3.8.4将制备卡平置于仪器上，制备卡的凹口要与仪器载台上的凸出位置对应（图12）。'
        hits = _simple_match(source, [{'text': template, 'id': 't'}], source_sentence=source)
        guide_hits = [item for item in hits if item.get('rule_source') == 'sentence_guide']
        self.assertTrue(guide_hits)
        self.assertEqual(guide_hits[0].get('category'), 'term')
        self.assertIn(guide_hits[0].get('category'), {
            'grammar', 'word', 'term', 'ambiguity', 'redundancy', 'logic', 'missing', 'risk',
        })

    def test_issue_meta_aggregates_guide_category(self):
        decision = SimpleNamespace(
            action='accept',
            paragraph_index=0,
            sentence_index=0,
            source_paragraph_index=0,
            original_text='将制备卡平置于机器上。',
            accepted_template='将制备卡平置于仪器上。',
            category='',
            severity='',
            candidate_text='将制备卡平置于仪器上。',
            rule_source='sentence_guide',
        )
        cached_items = [{
            'source_paragraph_index': 0,
            'sentence_index': 0,
            'original_text': '将制备卡平置于机器上。',
            'candidates': [{
                'category': 'term',
                'template_text': '将制备卡平置于仪器上。',
                'rule_source': 'sentence_guide',
            }],
        }]
        meta = polish_lab._cat_report_issue_meta(decision, cached_items)
        self.assertEqual(meta['category_key'], 'term')
        self.assertEqual(meta['category_label'], '术语')

    def test_colon_only_expiry_rewrite_is_trivial(self):
        source = '有效期：见试剂盒标签'
        template = '有效期见试剂盒标签。'
        self.assertTrue(_is_trivial_cat_artifact_edit(source, template))
        hits = _simple_match(source, [{'text': template, 'id': 'e'}], source_sentence=source)
        self.assertFalse(any(item.get('rule_source') == 'sentence_guide' for item in hits))

    def test_short_complete_spec_template_is_valid(self):
        template = '要求OD₂₆₀/OD₂₈₀=1.8~2.0。'
        self.assertTrue(polish_lab._is_valid_cat_template(template))
        self.assertGreaterEqual(len(polish_lab._normalize_cat_length_text(template)), 8)

    def test_embedded_spec_template_matches_long_source(self):
        source = '推荐使用完整度较好（无明显降解或轻微降解）且纯度良好（OD260/OD280=1.8 ~ 2.1，OD260/OD230＞2.0，RIN值>7）的高质量RNA样本。'
        template = '要求OD₂₆₀/OD₂₈₀=1.8~2.0，OD₂₆₀/OD₂₃₀＞2.0。'
        hits = _simple_match(source, [{'text': template, 'id': 'spec'}], source_sentence=source)
        self.assertTrue(hits)
        rewritten = polish_lab._normalize_cat_typography(hits[0]['template_text'])
        self.assertIn('1.8~2.0', rewritten.replace(' ', ''))
        self.assertIn('OD260/OD230', rewritten.replace(' ', ''))
        self.assertIn('RIN', rewritten)

    def test_thaw_template_keeps_single_method_and_kit_term(self):
        source = '试剂套装各组分使用前提前取出，室温解冻。'
        ice = '试剂盒各组分使用前提前取出，冰上解冻。'
        hits = _simple_match(source, [{'text': ice, 'id': 'thaw'}], source_sentence=source)
        for item in hits:
            text = item.get('template_text') or ''
            self.assertNotIn('试剂盒', text)
            self.assertFalse('冰上解冻' in text and '室温解冻' in text)

    def test_barcode_template_keeps_coverb_subject(self):
        source = '利用双barcode的矫正功能，最大程度上保证了测序数据拆分的均一性和准确性。'
        template = '利用双barcode的矫正功能，可最大程度保证测序数据拆分的均一性和准确性。'
        hits = _simple_match(source, [{'text': template, 'id': 'bc'}], source_sentence=source)
        self.assertTrue(hits)
        self.assertTrue(hits[0]['template_text'].startswith('利用'))

    def test_nested_card_template_beats_place_on(self):
        source = '1.操作指示卡使用之前请将操作指示卡正确的嵌套在制备卡上（图8）'
        nested = '操作指示卡需正确嵌套在样本制备卡上。'
        placed = '将操作指示卡放在样本制备卡上。'
        hits = _simple_match(
            source,
            [{'text': nested, 'id': 'nested'}, {'text': placed, 'id': 'placed'}],
            source_sentence=source,
        )
        self.assertTrue(hits)
        rewritten = hits[0]['template_text']
        self.assertIn('需正确嵌套', rewritten)
        self.assertNotIn('放在', rewritten)
        self.assertNotRegex(rewritten, r'。\s*（图8）')
        self.assertIn('（图8）', rewritten)

    def test_quote_normalized_read_list_template_matches(self):
        source = '注意：操作前请阅读附录Ⅰ以及附录Ⅱ'
        template = '操作前请阅读第22页“操作指示卡使用方法”以及第22页“试剂和样本加载介绍”。'
        hits = _simple_match(source, [{'text': template, 'id': 'read'}], source_sentence=source)
        self.assertTrue(hits)

    def test_paraphrase_keep_aligns_with_match_threshold(self):
        source = '将试剂按照下面的表格及体积转移到制备卡的特定孔位。'
        template = '将试剂按照表格加入到样本制备卡对应孔位。'
        hits = _simple_match(source, [{'text': template, 'id': 't'}], source_sentence=source)
        self.assertTrue(hits)
        kept = polish_lab._should_keep_text_manual_candidate(source, hits[0], ai_semantic_active=False)
        self.assertTrue(kept)

    def test_numbered_prefix_is_not_clause_splice(self):
        source = '1.选择合适的移液器，调整移液器至正确的量程，并且正确的插上移液器的枪头。'
        template = '选择合适的移液器，调整移液器至正确的量程，保证正确插入移液器吸头。'
        composed = _compose_cat_candidate_text(source, template)
        self.assertFalse(polish_lab._is_duplicated_clause_splice(source, composed, template))
        hits = _simple_match(source, [{'text': template, 'id': 'pipette'}], source_sentence=source)
        self.assertTrue(hits)

    def test_container_paraphrase_is_not_hard_conflict(self):
        source = '注意：加载样本和试剂时移液器要插到底，但是力气不可过大，避免破坏芯片'
        template = '加载试剂和样本时，移液器吸头应插到底，不可过于用力，避免损坏样本制备卡。'
        ok, reason = polish_lab._key_term_anchor_consistent(source, template)
        self.assertTrue(ok)
        self.assertEqual(reason, '')
        hits = _simple_match(source, [{'text': template, 'id': 'chip'}], source_sentence=source)
        self.assertTrue(hits)

    def test_compose_locks_reagent_name_token(self):
        source = '如B1-WGS-PCR代表该试剂应加载到操作指示卡上的B1孔位；'
        template = '如【B1-WGS-DNBB】代表该试剂应加载到操作指示卡上的B1孔位。'
        composed = _compose_cat_candidate_text(source, template)
        self.assertIn('B1-WGS-PCR', composed)
        self.assertNotIn('B1-WGS-DNBB', composed)
        hits = _simple_match(source, [{'text': template, 'id': 'reagent'}], source_sentence=source)
        for item in hits:
            self.assertIn('B1-WGS-PCR', item.get('template_text') or '')
            self.assertNotIn('B1-WGS-DNBB', item.get('template_text') or '')

    def test_compose_locks_kit_version_token(self):
        source = '取出DNBelab-D4RS样本制备套件A中的制备卡。'
        template = '取出DNBelab-D4RS样本制备卡套件B中的制备卡。'
        composed = _compose_cat_candidate_text(source, template)
        self.assertIn('样本制备套件A', composed)
        self.assertNotIn('套件B', composed)
        hits = _simple_match(source, [{'text': template, 'id': 'kit'}], source_sentence=source)
        for item in hits:
            text = item.get('template_text') or ''
            self.assertIn('套件A', text)
            self.assertNotIn('套件B', text)

    def test_punctuation_only_well_count_is_grammar(self):
        source = 'A346-WGS-EB代表该试剂应该加载到A3,A4,A6三个孔位。'
        revised = 'A346-WGS-EB代表该试剂应该加载到A3、A4、A6三个孔位。'
        self.assertEqual(
            polish_lab._cat_report_change_category(source, revised, 'modify'),
            'grammar',
        )

    def test_diagnose_locks_reagent_and_kit_tokens(self):
        reagent = _filter_cat_artifact_diagnoses(
            [{
                'sentence_index': 25,
                'quote': '实验前需提前将冷藏试剂中的两种磁珠（A18-WGS-BE和S1234-WGS-SPB）室温平衡半个小时。',
                'revised': '实验前需提前将冷藏试剂中的两种磁珠（A57-WGS-BE和S1234-WGS-SPB）室温平衡半个小时。',
                'category': 'term',
            }],
            [{'sentence_index': 25, 'source_sentence_text': '实验前需提前将冷藏试剂中的两种磁珠（A18-WGS-BE和S1234-WGS-SPB）室温平衡半个小时。'}],
        )
        self.assertEqual(reagent, [])
        kit = _filter_cat_artifact_diagnoses(
            [{
                'sentence_index': 31,
                'quote': '取出DNBelab-D4RS样本制备套件A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，录入制备卡信息。',
                'revised': '取出DNBelab-D4RS样本制备卡套件B中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，录入制备卡信息。',
                'category': 'term',
            }],
            [{'sentence_index': 31, 'source_sentence_text': '取出DNBelab-D4RS样本制备套件A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，录入制备卡信息。'}],
        )
        self.assertEqual(kit, [])

    def test_compose_trims_duplicated_search_clause(self):
        duplicated = '搜索货号或产品名，搜索货号或产品名，下载说明书。'
        self.assertEqual(
            polish_lab._trim_duplicated_leading_clause(duplicated),
            '搜索货号或产品名，下载说明书。',
        )
        source = '搜索货号或产品名，下载最新版说明书。'
        template = '搜索货号或产品名，下载说明书。'
        composed = _compose_cat_candidate_text(source, template)
        self.assertEqual(composed.count('搜索货号或产品名'), 1)

    def test_reapply_collapses_duplicated_notice_prefix(self):
        original = '注意：操作前请阅读附录Ⅰ以及附录Ⅱ'
        doubled = _reapply_sentence_prefix(original, '注意:操作前请阅读附录A以及附录B。')
        self.assertEqual(doubled.count('注意'), 1)
        self.assertTrue(doubled.startswith('注意：'))
        collapsed = polish_lab._trim_duplicated_leading_clause('注意：注意：操作前请阅读附录A以及附录B。')
        self.assertEqual(collapsed, '注意：操作前请阅读附录A以及附录B。')

    def test_compose_restores_meta_case(self):
        source = '本试剂套装适用于人、鼠 total RNA样本、Meta、病原微生物RNA等。'
        lowered = '本试剂套装适用于人、鼠 total RNA样本、meta、病原微生物RNA等。'
        composed = _compose_cat_candidate_text(source, lowered)
        self.assertIn('Meta', composed)
        self.assertNotIn('meta', composed)
        self.assertTrue(polish_lab._drops_protected_latin_terms(source, lowered))
        hits = _simple_match(source, [{'text': lowered, 'id': 'meta'}], source_sentence=source)
        for item in hits:
            self.assertIn('Meta', item.get('template_text') or '')
            self.assertNotIn('meta', item.get('template_text') or '')


if __name__ == '__main__':
    unittest.main()
