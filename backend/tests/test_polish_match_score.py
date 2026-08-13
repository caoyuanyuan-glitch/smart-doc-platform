import builtins
import json
import asyncio
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.api.polish import (  # noqa: E402
    _apply_skill_polish,
    _ai_style_guide_text,
    _compact_document_ai_style_guide,
    _collect_text_polish_cat_items,
    _build_document_feedback_record_key,
    _document_feedback_stats,
    _feedback_accuracy_percent,
    _extract_style_rules,
    _filter_visible_doc_changes,
    _filter_candidate_templates,
    _three_tier_match,
    _top_template_candidates,
    _is_pooling_platform_sentence,
    _split_pooling_sentence_windows,
    _build_visible_change_entry,
    _cat_match_score,
    _filter_candidate_templates,
    _ai_semantic_rerank_candidates,
    _apply_constraint_polish,
    _best_pooling_clause_template,
    _build_change_match_detail,
    _build_sentence_review_detail,
    _template_replace_guard,
    _is_low_value_doc_change,
    _looks_like_title_or_noun_phrase,
    _preferred_entries_from_guide,
    _preferred_entries_cache,
    _sentence_candidate_pool_cache,
    _sentence_top_candidates_cache,
    _normalize_doc_ai_line,
    _normalize_doc_polished_text,
    _reapply_sentence_prefix,
    _lightweight_operation_review_suggestion,
    _is_simple_operation_sentence,
    _should_skip_expensive_template_match,
    _should_use_lightweight_review_detail,
    _simple_match,
    _normalize_review_suggestion,
    _should_emit_reference_review_change,
    _style_rules_cache,
    _simple_match,
)
from app.utils.instrument_polisher import instrument_polish_engine  # noqa: E402
from app.models.polish_feedback import PolishFeedback  # noqa: E402


class PolishMatchScoreRegressionTest(unittest.TestCase):
    def test_feedback_accuracy_percent_uses_submitted_rating_value(self):
        record = PolishFeedback(accuracy=80, processed_count=1, target='sentence_guide')

        self.assertEqual(_feedback_accuracy_percent(record), 80.0)

    def test_bundled_structured_guide_contains_recent_pdf_templates(self):
        guide_path = BACKEND_ROOT / 'app' / 'static' / 'bundled' / 'structured_sentence_guide_d4rs_operations.md'
        guide_text = guide_path.read_text(encoding='utf-8')

        entries = _preferred_entries_from_guide(guide_text)
        candidate_texts = [entry.get('template_text', '') if isinstance(entry, dict) else str(entry) for entry in entries]

        self.assertIn('部分试剂会加多个孔位，请按指示添加。', candidate_texts)
        self.assertIn('将加液装置插入进液孔 SF/F3。', candidate_texts)
        self.assertIn('没有气泡方可进行后续操作。', candidate_texts)
        self.assertIn('参数确认无误后，点击运行。', candidate_texts)

    def test_display_percent_is_capped_for_spacing_and_number_cases(self):
        cases = [
            ('样本量为160 bp。', '样本量为 160 bp。'),
            ('样本量为1 60 bp。', '样本量为 160 bp。'),
            ('产品型号为DNBelab-D4RS。', '产品型号为 DNBelab-D4RS。'),
            ('请参考说明书 H-020-001198-00。', '请参考说明书 H-020-001198-00。'),
        ]

        for before, after in cases:
            with self.subTest(before=before, after=after):
                score = _cat_match_score(before, after)
                self.assertLessEqual(score['overall_percent'], 100)
                self.assertLessEqual(score['overall_score'], 1.0)
                self.assertLessEqual(score['ranking_score'], 1.0)

    def test_bonus_signals_are_reflected_in_display_and_ranking_scores(self):
        score = _cat_match_score(
            '在样本制备卡准备界面点击按钮，进入制备卡安装界面。',
            '点击按钮，进入制备卡安装界面。'
        )

        self.assertLess(score['overall_percent'], 100)
        self.assertEqual(score['raw_score'], score['display_raw_score'])
        self.assertEqual(score['overall_score'], score['ranking_score'])
        self.assertGreater(score['ranking_score'], 0)
        self.assertGreater(score['term_anchor_score'], 0)

    def test_penalty_signals_reduce_ranking_score_from_display_score(self):
        score = _cat_match_score(
            '样本量为 160 bp。',
            '样本量为 260 bp。'
        )

        self.assertGreater(score['penalty_score'], 0)
        self.assertIn('数字/单位不一致', score['penalty_reasons'])
        self.assertLess(score['ranking_score'], score['display_raw_score'])

    def test_sentence_review_detail_uses_ranking_score_for_auto_apply(self):
        from unittest.mock import patch

        with patch('app.api.polish._build_change_match_detail', return_value={
            'overall_score': 1.0,
            'overall_percent': 100,
            'ranking_score': 0.94,
            'display_raw_score': 1.0,
            'penalty_score': 0.06,
            'penalty_reasons': ['数字/单位不一致'],
            'segment_scores': {},
        }):
            detail, after = _build_sentence_review_detail('样本量为 160 bp。', '样本量为 260 bp。', '', 'style', '句式模板匹配')

        self.assertEqual(after, '样本量为 260 bp。')
        self.assertFalse(detail.get('auto_applied'))
        self.assertEqual(detail.get('review_mode'), 'manual')

    def test_composition_sentence_is_not_misclassified_as_title(self):
        sentence = 'DNBelab-D4RS RNA文库制备试剂盒套装由3个独立盒子包装。具体货号、组分信息见表1。'
        self.assertFalse(_looks_like_title_or_noun_phrase(sentence))

    def test_composition_sentence_can_recall_reference_template(self):
        guide_text = '''
## 建库试剂句子分类汇总

| 类别 | 推荐句式 |
| --- | --- |
| 套装组成 | 本试剂套装由3个独立盒子包装组成。具体货号、组分信息见下表： |
'''
        sentence = 'DNBelab-D4RS RNA文库制备试剂盒套装由3个独立盒子包装。具体货号、组分信息见表1。'

        entries = _preferred_entries_from_guide(guide_text)
        candidates = _filter_candidate_templates(sentence, entries)

        self.assertTrue(candidates)
        self.assertIn('本试剂套装由3个独立盒子包装组成。具体货号、组分信息见下表：', candidates[0])

    def test_short_step_title_is_recognized_as_title(self):
        sentence = '3.9 DNB取出'
        self.assertTrue(_looks_like_title_or_noun_phrase(sentence))

    def test_colon_operation_sentence_is_not_misclassified_as_title(self):
        sentence = '参数设置如下：确认孔位对应关系后点击运行'
        self.assertFalse(_looks_like_title_or_noun_phrase(sentence))

    def test_constraint_polish_keeps_predicate_wei_clause(self):
        sentence = '每个产物为一对barcode序列组合'
        self.assertEqual(_apply_constraint_polish(sentence), sentence)

    def test_constraint_polish_keeps_color_predicate_clause(self):
        sentence = '注意：吸取DNB时会带出封闭液，封闭液为红色，DNB为无色，目测无色液体体积在10µL-15µL左右则表示DNB完全吸出'
        self.assertEqual(_apply_constraint_polish(sentence), sentence)

    def test_should_skip_expensive_template_match_for_generic_ui_navigation(self):
        sentence = '点击DNBelab-D4RS制备系统界面上 按钮，进入试剂盒信息录入界面（图3）。'
        self.assertTrue(_should_skip_expensive_template_match(sentence))

    def test_should_skip_expensive_template_match_for_login_flow(self):
        sentence = '实验前请打开DNBelab-D4RS样本制备系统电源，进入仪器登入界面，输入用户名和密码进入建库界面（图1），并确保仪器能够正常运行。'
        self.assertTrue(_should_skip_expensive_template_match(sentence))

    def test_lightweight_operation_review_suggestion_normalizes_luru_to_shuru(self):
        sentence = '3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'

        suggestion = _lightweight_operation_review_suggestion(sentence)

        self.assertIn('信息输入界面', suggestion)

    def test_is_simple_operation_sentence_matches_generic_step_sentence(self):
        sentence = '3.9.1待仪器脚本运行完成，打开仪器载台盖板，将制备卡载台抽出。'

        self.assertTrue(_is_simple_operation_sentence(sentence))

    def test_is_simple_operation_sentence_excludes_pooling_sentence(self):
        sentence = '根据选择的测序平台及对应样品的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂盒已将PCRmix1-4及PCRmix5-8四个为一组预设为平衡碱基barcode组合，即可以单张D4芯片4样本，或者二张D4芯片8样本混样上机。'

        self.assertFalse(_is_simple_operation_sentence(sentence))

    def test_should_not_skip_expensive_template_match_for_recallable_operation_sentence(self):
        sentence = '试剂套装各组分使用前提前取出，室温解冻。解冻后用漩涡混匀仪充分混匀，瞬时离心后置于冰上待用。'
        self.assertFalse(_should_skip_expensive_template_match(sentence))

    def test_apply_skill_polish_skips_heavy_template_match_for_generic_ui_navigation(self):
        sentence = '点击DNBelab-D4RS制备系统界面上 按钮，进入试剂盒信息录入界面（图3）。'
        guide_text = '''
## 推荐句式

- 点击【试剂盒信息】按钮，进入试剂盒信息录入界面。
'''
        from unittest.mock import patch

        with patch('app.api.polish._best_guarded_match', side_effect=AssertionError('should not call')):
            polished, changes = _apply_skill_polish(sentence, {}, None, sentence_guide=guide_text)

        self.assertEqual(polished, sentence)
        self.assertEqual(changes, [])

    def test_filter_candidate_templates_prioritizes_slot_sample_mapping_templates(self):
        sentence = '将以上配制好的样品（10μL）全部转移到制备卡上对应的进样孔中（S1-S4），S1对应sample1，S2对应sample2，S3对应sample3，S4对应sample4。'
        templates = [
            '孔位E1对应sample 1',
            '孔位E2对应sample 2',
            '孔位E3对应sample 3',
            '孔位E4对应sample 4',
            '参数确认无误后，点击运行。',
            '将制备卡水平置于载台上。',
        ]

        pool = _filter_candidate_templates(sentence, templates)

        self.assertTrue(pool)

    def test_collect_text_polish_cat_items_returns_manual_candidates_for_text_endpoint(self):
        from app.database import SessionLocal

        guide_text = (BACKEND_ROOT / 'app' / 'static' / 'bundled' / 'structured_sentence_guide_d4rs_operations.md').read_text(encoding='utf-8')

        db = SessionLocal()
        try:
            original = '运输温度为-80℃~-15℃时，需使用干冰运输，且需要在收到产品时检查是否还有剩余干冰。'
            cat_items = asyncio.run(_collect_text_polish_cat_items(
                original,
                db,
                sentence_guide=guide_text,
                terminology_md='',
                sentence_file_id=None,
            ))
        finally:
            db.close()

        self.assertTrue(cat_items)
        first_item = cat_items[0]
        self.assertEqual(first_item.get('original_text'), original)
        self.assertTrue(first_item.get('candidates'))
        self.assertTrue(any('检查是否还有剩余干冰' in str(item.get('raw_template_text', '') or item.get('template_text', '')) for item in first_item.get('candidates', [])))

    def test_collect_text_polish_cat_items_returns_empty_for_unmatched_text(self):
        from app.database import SessionLocal

        guide_text = (BACKEND_ROOT / 'app' / 'static' / 'bundled' / 'structured_sentence_guide_d4rs_operations.md').read_text(encoding='utf-8')

        db = SessionLocal()
        try:
            original = '这是一个完全没有 CAT 模板命中的普通句子。'
            cat_items = asyncio.run(_collect_text_polish_cat_items(
                original,
                db,
                sentence_guide=guide_text,
                terminology_md='',
                sentence_file_id=None,
            ))
        finally:
            db.close()

        self.assertEqual(cat_items, [])

    def test_text_manual_candidate_can_change_displayed_result(self):
        original = '实验前请熟悉和掌握需使用的各种仪器的操作方法和注意事项。'
        candidate = '实验前请熟悉需使用的各种仪器的注意事项，并掌握其操作方法。'

        self.assertNotEqual(original, candidate)

    def test_build_change_match_detail_uses_lightweight_detail_for_slot_sample_mapping(self):
        before = '3.7.3将以上配制好的样品（10μL）全部转移到制备卡上对应的进样孔中（S1-S4），S1对应sample1，S2对应sample2，S3对应sample3，S4对应sample4。'
        after = '3.7.3将以上配制好的样品（10μL）全部转移到制备卡上对应的进样孔中（S1-S4），孔位E1对应sample 1，孔位E2对应sample 2，孔位E3对应sample 3，孔位E4对应sample 4。'

        detail = _build_change_match_detail(before, after, 'style', '句式模板匹配')

        self.assertIsNotNone(detail)
        self.assertIn('结构化映射句轻量评估', detail.get('label', ''))
        self.assertTrue(detail['segment_scores']['object']['applicable'])
        self.assertGreater(detail.get('overall_percent', 0), 0)

    def test_build_change_match_detail_uses_lightweight_detail_for_generic_ui_navigation(self):
        before = '3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'
        after = '3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息输入界面（图2）。'

        detail = _build_change_match_detail(before, after, 'style', '句式模板匹配')

        self.assertIsNotNone(detail)
        self.assertIn('操作界面句轻量评估', detail.get('label', ''))
        self.assertGreater(detail.get('overall_percent', 0), 0)

    def test_build_change_match_detail_uses_lightweight_detail_for_terminology_change(self):
        before = '3.9.2利用阔口枪头将产物孔D1-4的DNB吸出（枪头垂直插入产物孔），转移到PCR管中。'
        after = '3.9.2利用阔口吸头将产物孔D1-4的DNB吸出（吸头垂直插入产物孔），转移到PCR管中。'

        detail = _build_change_match_detail(before, after, 'terminology', '术语替换')

        self.assertIsNotNone(detail)
        self.assertIn('术语替换轻量评估', detail.get('label', ''))
        self.assertGreater(detail.get('overall_percent', 0), 0)

    def test_filter_candidate_templates_prioritizes_pooling_platform_templates(self):
        sentence = '根据选择的测序平台及对应样品的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂盒已将PCRmix1-4及PCRmix5-8四个为一组预设为平衡碱基barcode组合。'
        templates = [
            '根据选择的测序平台及对应样本的数据量需求，进行混样测序。',
            '为保证测序碱基平衡，本试剂套装已将PCRmix1-4及PCRmix5-8，4个为一组预设为平衡碱基barcode组合。',
            '本试剂套装8管PCRmix对应的barcode编号如下表所示。',
            '将制备卡水平置于载台上。',
            '参数确认无误后，点击运行。',
        ]

        pool = _filter_candidate_templates(sentence, templates)

        self.assertGreaterEqual(len(pool), 3)
        self.assertIn('根据选择的测序平台及对应样本的数据量需求，进行混样测序。', pool)
        self.assertIn('为保证测序碱基平衡，本试剂套装已将PCRmix1-4及PCRmix5-8，4个为一组预设为平衡碱基barcode组合。', pool)
        self.assertNotIn('将制备卡水平置于载台上。', pool)

    def test_is_pooling_platform_sentence_uses_structural_signals(self):
        sentence = '按所选仪器及数据需求合并上机，为保证序列平衡，将A1-A4与B1-B4分组组合；可4个样本上机，或者8个样本上机，编号见下表。'

        self.assertTrue(_is_pooling_platform_sentence(sentence))

    def test_is_pooling_platform_sentence_does_not_capture_generic_operation_sentence(self):
        sentence = '使用移液枪加载样本到制备卡时，要把移液枪插到底，并且倾斜移液枪大概30°，使出液方向指向制备卡的左侧；使用移液枪加载试剂到制备卡时，要把移液枪插到底，并且倾斜移液枪大概30°，使出液方向指向制备卡的右侧（如图16）。'

        self.assertFalse(_is_pooling_platform_sentence(sentence))

    def test_best_pooling_clause_template_blocks_excessive_expansion(self):
        sentence = '搭配DNBSEQ-G99测序时建议每个样品DNB投入量5.25μL。'
        templates = [
            '若搭配DNBSEQ-G99RS测序，建议每个样本的DNB投入量为5.25 μL（结果页面中的每个通道的推荐投入量为5.25 μL），4个样本一共21 μL DNB。'
        ]

        tmpl, score, level = _best_pooling_clause_template(sentence, templates)

        self.assertEqual((tmpl, score, level), (None, 0.0, 'NONE'))

    def test_split_pooling_sentence_windows_merges_intro_and_conjunction_clauses(self):
        sentence = '按所选仪器及数据需求合并上机，为保证序列平衡，将A1-A4与B1-B4分组组合，可4个样本上机，或者8个样本上机；编号见下表。'

        windows = _split_pooling_sentence_windows(sentence)

        self.assertTrue(any('按所选仪器及数据需求合并上机，为保证序列平衡' in item for item in windows))
        self.assertTrue(any('可4个样本上机，或者8个样本上机' in item for item in windows))

    def test_build_change_match_detail_uses_lightweight_detail_for_pooling_platform_sentence(self):
        before = '根据选择的测序平台及对应样品的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂盒已将PCRmix1-4及PCRmix5-8四个为一组预设为平衡碱基barcode组合，即可以单张D4芯片4样本，或者二张D4芯片8样本混样上机。'
        after = '根据选择的测序平台及对应样本的数据量需求，进行混样测序。为保证测序碱基平衡，本试剂套装已将PCRmix1-4及PCRmix5-8，4个为一组预设为平衡碱基barcode组合。即可以1张样本制备卡4样本混样上机，或者2张样本制备卡8样本混样上机。'

        detail = _build_change_match_detail(before, after, 'style', '句式模板匹配')

        self.assertIsNotNone(detail)
        self.assertIn('混样/平台长句轻量评估', detail.get('label', ''))
        self.assertTrue(detail['segment_scores']['object']['applicable'])
        self.assertGreater(detail.get('overall_percent', 0), 0)

    def test_apply_skill_polish_matches_multiple_pooling_clauses(self):
        sentence = '根据选择的测序平台及对应样品的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂盒已将PCRmix1-4及PCRmix5-8四个为一组预设为平衡碱基barcode组合，即可以单张D4芯片4样本，或者二张D4芯片8样本混样上机；本试剂盒8管PCRmix对应的barcode编号如下表。'
        guide_text = '''
## 推荐句式

- 根据选择的测序平台及对应样本的数据量需求，进行混样测序。
- 为保证测序碱基平衡，本试剂套装已将PCRmix1-4及PCRmix5-8，4个为一组预设为平衡碱基barcode组合。
- 即可以1张样本制备卡4样本混样上机，或者2张样本制备卡8样本混样上机。
- 本试剂套装8管PCRmix对应的barcode编号如下表所示。
'''

        from unittest.mock import patch

        with patch('app.api.polish._ai_semantic_rerank_candidates', side_effect=lambda _sentence, ranked: ranked):
            polished, changes = _apply_skill_polish(sentence, {}, None, sentence_guide=guide_text)

        self.assertIn('对应样本的数据量需求', polished)
        self.assertIn('本试剂套装已将PCRmix1-4及PCRmix5-8，4个为一组预设为平衡碱基barcode组合', polished)
        self.assertIn('1张样本制备卡4样本混样上机', polished)
        self.assertIn('本试剂套装8管PCRmix对应的barcode编号如下表所示。', polished)
        self.assertNotIn('。，', polished)
        self.assertNotIn('。。', polished)
        self.assertTrue(changes)

    def test_should_use_lightweight_review_detail_for_pooling_sentence_when_visible_text_unchanged(self):
        original = '4. 根据选择的测序平台及对应样品的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂盒已将PCRmix1-4及PCRmix5-8四个为一组预设为平衡碱基barcode组合，即可以单张D4芯片4样本，或者二张D4芯片8样本混样上机；本试剂盒8管PCRmix对应的barcode编号如下表。'
        intermediate = '4. 根据选择的测序平台及对应样本的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂套装已将PCRmix1-4及PCRmix5-8，4个为一组预设为平衡碱基barcode组合，即可以1张样本制备卡4样本混样上机，或者2张样本制备卡8样本混样上机；本试剂套装8管PCRmix对应的barcode编号如下表所示。'

        self.assertTrue(_should_use_lightweight_review_detail(original, original))
        self.assertFalse(_should_use_lightweight_review_detail(original, intermediate))

    def test_normalize_review_suggestion_can_drop_pooling_sentence_rewrite(self):
        original = '4. 根据选择的测序平台及对应样品的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂盒已将PCRmix1-4及PCRmix5-8四个为一组预设为平衡碱基barcode组合，即可以单张D4芯片4样本，或者二张D4芯片8样本混样上机；本试剂盒8管PCRmix对应的barcode编号如下表。'
        suggestion = '4. 根据选择的测序平台及对应样本的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂套装已将PCRmix1-4及PCRmix5-8，4个为一组预设为平衡碱基barcode组合，即可以1张样本制备卡4样本混样上机，或者2张样本制备卡8样本混样上机；本试剂套装8管PCRmix对应的barcode编号如下表所示。'

        normalized = _normalize_review_suggestion(original, suggestion, 'style', '句式模板匹配')

        self.assertEqual(normalized, '')

    def test_field_style_colon_rewrite_is_hidden_in_review_detail(self):
        before = '2. 每个产物为一对barcode序列组合，测序完成后可拆分出4个barcode；进行数据分析时需将4个barcode合并以免造成对应样本数据量损失。'
        suggestion = '2. 每个产物：一对barcode序列组合，测序完成后可拆分出4个barcode；进行数据分析时需将4个barcode合并以免造成对应样本数据量损失。'
        detail, after = _build_sentence_review_detail(before, suggestion, '', 'style', '句式模板匹配')
        self.assertEqual(after, before)
        self.assertEqual(detail.get('suggested_text'), before)
        self.assertFalse(detail.get('has_change'))

    def test_multi_field_style_colon_rewrite_is_hidden_in_review_detail(self):
        before = '注意：吸取DNB时会带出封闭液，封闭液为红色，DNB为无色，目测无色液体体积在10µL-15µL左右则表示DNB完全吸出'
        suggestion = '注意：吸取DNB时会带出封闭液，封闭液：红色，DNB：无色，目测无色液体体积在10 µL-15 µL左右则表示DNB完全吸出'
        detail, after = _build_sentence_review_detail(before, suggestion, '', 'style', '句式模板匹配')
        self.assertEqual(after, before)
        self.assertEqual(detail.get('suggested_text'), before)
        self.assertFalse(detail.get('has_change'))

    def test_multi_field_style_colon_rewrite_is_hidden_in_visible_change_entry(self):
        before = '注意：吸取DNB时会带出封闭液，封闭液为红色，DNB为无色，目测无色液体体积在10µL-15µL左右则表示DNB完全吸出'
        suggestion = '注意：吸取DNB时会带出封闭液，封闭液：红色，DNB：无色，目测无色液体体积在10 µL-15 µL左右则表示DNB完全吸出'
        self.assertIsNone(_build_visible_change_entry(1, before, suggestion, 'style', '句式模板匹配'))

    def test_guard_rejected_irrelevant_candidate_is_not_returned(self):
        before = '3.6.2将操作指示卡放置在制备卡上。（图7）'
        templates = [
            '本说明书中的所有图片均为示意图，图片内容可能与实物有细微差异，请以购买的产品为准。'
        ]
        candidates = _top_template_candidates(before, templates, limit=5)
        self.assertEqual(candidates, [])

    def test_operation_card_sentence_can_recall_guarded_candidate_from_synonym_template(self):
        guide_text = '''
## 推荐句式

| 模板编号 | 标准句式 | 句子类型 | 动作词 | 核心对象 | 前置条件 | 结果或状态 | 同义表达 | 是否自动替换 | 守卫说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-5.3.1-04 | 将操作指示卡放在样本制备卡上。 | action | 放 | 操作指示卡;样本制备卡 |  | 操作指示卡放置完成 | 放上=放在…上;放置在=放在;制备卡=样本制备卡 | yes | 对象必须同时包含操作指示卡和样本制备卡 |
'''
        sentence = '3.6.2将操作指示卡放置在制备卡上。（图7）'

        entries = _preferred_entries_from_guide(guide_text)

        from unittest.mock import patch
        with patch('app.api.polish._ai_semantic_rerank_candidates', side_effect=lambda _sentence, ranked: ranked):
            candidates = _top_template_candidates(sentence, entries, limit=5)

        self.assertTrue(candidates)
        self.assertTrue(candidates[0].get('guard_passed'))
        self.assertEqual(candidates[0].get('template'), '将操作指示卡放在样本制备卡上。')

    def test_three_tier_match_hits_l1_5_after_synonym_normalization(self):
        sentence = '点击确认按钮，切换到样本管理界面。'
        templates = ['单击确定按钮，进入样本管理界面。']

        template, score, match_level = _three_tier_match(sentence, templates)

        self.assertEqual(template, '单击确定按钮，进入样本管理界面。')
        self.assertEqual(match_level, 'L1.5')
        self.assertEqual(score, 0.95)

    def test_clause_sentence_can_recall_split_candidate(self):
        guide_path = BACKEND_ROOT / 'app' / 'static' / 'bundled' / 'structured_sentence_guide_d4rs_operations.md'
        guide_text = guide_path.read_text(encoding='utf-8')
        entries = _preferred_entries_from_guide(guide_text)
        sentence = '没有气泡再进行后续操作'

        from unittest.mock import patch
        with patch('app.api.polish._ai_semantic_rerank_candidates', side_effect=lambda _sentence, ranked: ranked):
            candidates = _top_template_candidates(sentence, entries, limit=5)

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].get('template'), '没有气泡方可进行后续操作。')
        self.assertGreaterEqual(int(candidates[0].get('overall_percent', 0) or 0), 20)

    def test_time_limit_clause_can_recall_split_candidate(self):
        guide_path = BACKEND_ROOT / 'app' / 'static' / 'bundled' / 'structured_sentence_guide_d4rs_operations.md'
        guide_text = guide_path.read_text(encoding='utf-8')
        entries = _preferred_entries_from_guide(guide_text)
        sentence = '建议10分钟之内完成'

        from unittest.mock import patch
        with patch('app.api.polish._ai_semantic_rerank_candidates', side_effect=lambda _sentence, ranked: ranked):
            candidates = _top_template_candidates(sentence, entries, limit=5)

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].get('template'), '建议在 10 分钟内完成。')
        self.assertGreaterEqual(int(candidates[0].get('overall_percent', 0) or 0), 20)

    def test_platform_feedback_bullet_sentences_are_recallable(self):
        guide_text = '''
## 候选召回句式库

# 平台反馈的句式清单

## 用户反馈修正

- 注意：封闭液填装完成之后，需要观察制备卡中是否有气泡。没有气泡方可进行后续操作。
- 禁止在维护或运输过程中使用本仪器。

## 仅供 AI 润色的通用风格指南

请保持专业客观。
'''

        entries = _preferred_entries_from_guide(guide_text)
        candidate_texts = [entry.get('template_text', '') if isinstance(entry, dict) else str(entry) for entry in entries]

        self.assertIn('注意：封闭液填装完成之后，需要观察制备卡中是否有气泡。没有气泡方可进行后续操作。', candidate_texts)
        self.assertIn('没有气泡方可进行后续操作', candidate_texts)
        self.assertIn('禁止在维护或运输过程中使用本仪器。', candidate_texts)

    def test_preferred_entries_from_guide_reuses_cached_parse_result(self):
        guide_text = '''
## 候选召回句式库

## 用户反馈修正

- 测试缓存句式 A。
- 测试缓存句式 B。
'''

        _preferred_entries_cache.clear()
        _style_rules_cache.clear()
        _sentence_candidate_pool_cache.clear()
        _sentence_top_candidates_cache.clear()

        from unittest.mock import patch

        with patch('app.api.polish._extract_style_rules', wraps=_extract_style_rules) as mocked_extract:
            first = _preferred_entries_from_guide(guide_text)
            second = _preferred_entries_from_guide(guide_text)

        self.assertEqual(first, second)
        self.assertEqual(mocked_extract.call_count, 1)

    def test_build_sentence_review_detail_reuses_cached_top_candidates(self):
        guide_text = '''
## 用户反馈修正

- 部分试剂会加多个孔位，请按指示添加。
- 部分试剂需要加多个孔位，按照要求加到相应位置。
'''
        before = '注意：部分试剂会加多个孔位，按要求添加即可'

        _preferred_entries_cache.clear()
        _style_rules_cache.clear()
        _sentence_candidate_pool_cache.clear()
        _sentence_top_candidates_cache.clear()

        from unittest.mock import patch

        with patch('app.api.polish._top_template_candidates', wraps=_top_template_candidates) as mocked_top, \
             patch('app.api.polish._ai_semantic_rerank_candidates', side_effect=lambda _sentence, ranked: ranked):
            _build_sentence_review_detail(before, '', guide_text, 'style', '句式模板匹配')
            _build_sentence_review_detail(before, '', guide_text, 'style', '句式模板匹配')

        self.assertEqual(mocked_top.call_count, 1)

    def test_build_sentence_review_detail_skips_candidate_lookup_for_generic_ui_navigation(self):
        from unittest.mock import patch

        before = '3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息录入界面（图2）。'
        suggestion = '3.2.1.点击DNBelab-D4RS制备系统界面上按钮，进入样本制备卡信息输入界面（图2）。'

        with patch('app.api.polish._guide_top_template_candidates', side_effect=AssertionError('should not call')):
            detail, after = _build_sentence_review_detail(before, suggestion, 'mock-guide', 'style', '句式模板匹配')

        self.assertEqual(after, suggestion)
        self.assertEqual(detail.get('candidates', []), [])
        self.assertIn('操作界面句轻量评估', detail.get('label', ''))

    def test_build_sentence_review_detail_skips_candidate_lookup_for_terminology_change(self):
        from unittest.mock import patch

        before = '3.9.2利用阔口枪头将产物孔D1-4的DNB吸出（枪头垂直插入产物孔），转移到PCR管中。'
        suggestion = '3.9.2利用阔口吸头将产物孔D1-4的DNB吸出（吸头垂直插入产物孔），转移到PCR管中。'

        with patch('app.api.polish._guide_top_template_candidates', side_effect=AssertionError('should not call')):
            detail, after = _build_sentence_review_detail(before, suggestion, 'mock-guide', 'terminology', '术语替换')

        self.assertEqual(after, suggestion)
        self.assertEqual(detail.get('candidates', []), [])
        self.assertIn('术语替换轻量评估', detail.get('label', ''))

    def test_ai_style_guide_text_excludes_candidate_recall_section(self):
        guide_text = '''
## 候选召回句式库

## 用户反馈修正

- 没有气泡方可进行后续操作。

## 额外润色要求

统一使用主动语态。

## 仅供 AI 润色的通用风格指南

请保持句子简洁。
'''

        ai_guide = _ai_style_guide_text(guide_text)

        self.assertIn('请保持句子简洁。', ai_guide)
        self.assertNotIn('没有气泡方可进行后续操作。', ai_guide)

    def test_compact_document_ai_style_guide_keeps_requirements_and_hard_rules(self):
        guide_text = '''
## 候选召回句式库

- 没有气泡方可进行后续操作。

## 额外润色要求

统一使用主动语态，保留原始术语。

## 仅供 AI 润色的通用风格指南

## 前置指令（优先级覆盖所有后续规则）

1. 句子长度不超过 100 字。
2. 所有句子使用主动语态。
3. 句式学模板结构，内容保留原文。

## 一、禁用词

这里是很长的补充说明。
'''

        compact_guide = _compact_document_ai_style_guide(guide_text)

        self.assertIn('统一使用主动语态，保留原始术语。', compact_guide)
        self.assertIn('1. 句子长度不超过 100 字。', compact_guide)
        self.assertIn('3. 句式学模板结构，内容保留原文。', compact_guide)
        self.assertNotIn('这里是很长的补充说明。', compact_guide)

    def test_should_emit_reference_review_change_for_unchanged_paragraph(self):
        self.assertTrue(
            _should_emit_reference_review_change(
                '原句',
                '原句',
                '推荐句式',
                'style',
                '句式模板匹配',
            )
        )

    def test_should_emit_reference_review_change_for_low_value_polish(self):
        self.assertTrue(
            _should_emit_reference_review_change(
                '注意：部分试剂会加多个孔位，按要求添加即可',
                '注意：部分试剂会加多个孔位，按要求添加即可。',
                '注意：部分试剂需要加多个孔位，按照要求加到相应位置。',
                'style',
                '句式模板匹配',
            )
        )

    def test_filter_visible_doc_changes_keeps_existing_match_detail(self):
        changes = _filter_visible_doc_changes([
            {
                'before': '原句',
                'after': '建议句',
                'type': 'style',
                'rule_name': '句式模板匹配',
                'match_detail': {
                    'suggested_text': '人工建议句',
                    'overall_percent': 92,
                    'has_change': True,
                    'candidates': [],
                },
            }
        ])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['match_detail']['suggested_text'], '人工建议句')
        self.assertEqual(changes[0]['match_detail']['overall_percent'], 92)

    def test_guard_rejected_manual_candidate_can_still_be_returned_for_reference(self):
        before = '注意：部分试剂会加多个孔位，按要求添加即可'
        templates = ['部分试剂会加多个孔位，请按指示添加。']
        candidates = _top_template_candidates(before, templates, limit=5)
        self.assertTrue(candidates)
        self.assertFalse(candidates[0].get('guard_passed'))
        self.assertGreaterEqual(int(candidates[0].get('overall_percent', 0) or 0), 20)

    def test_filter_candidate_templates_uses_similarity_fallback(self):
        sentence = '注意：部分试剂会加多个孔位，按要求添加即可'
        templates = [
            '部分试剂会加多个孔位，请按指示添加。',
            '部分试剂需要加多个孔位，按照要求加到相应位置。',
            '将产物转移至新的离心管中。',
            '孔位较多时，请按照对应要求完成加样。',
        ]
        pool = _filter_candidate_templates(sentence, templates)
        self.assertGreaterEqual(len(pool), 3)
        self.assertIn('部分试剂会加多个孔位，请按指示添加。', pool)
        self.assertIn('部分试剂需要加多个孔位，按照要求加到相应位置。', pool)

    def test_simple_match_keeps_short_slot_mapping_candidate(self):
        sentence = 'S1对应sample1，S2对应sample2，S3对应sample3，S4对应sample4。'
        templates = [
            {'text': '孔位E1对应sample 1', 'id': '1'},
            {'text': '孔位E2对应sample 2', 'id': '2'},
            {'text': '孔位E3对应sample 3', 'id': '3'},
            {'text': '孔位E4对应sample 4', 'id': '4'},
        ]

        candidates = _simple_match(sentence, templates)

        self.assertTrue(candidates)
        self.assertTrue(any('孔位E1对应sample 1' == item.get('raw_template_text') for item in candidates))

    def test_simple_match_keeps_temperature_range_candidate(self):
        sentence = '运输温度为-80℃~-15℃时，需使用干冰运输。'
        templates = [
            {'text': '当运输温度为-80℃~-15℃时，需使用干冰运输', 'id': 'a'},
            {'text': '运输温度为-80℃~-15℃时，需使用干冰运输，且需要在收到产品时检查是否还有剩余干冰。', 'id': 'b'},
        ]

        candidates = _simple_match(sentence, templates)

        self.assertTrue(candidates)
        self.assertTrue(any('干冰运输' in item.get('template_text', '') for item in candidates))

    def test_review_detail_does_not_fallback_to_guard_rejected_candidate(self):
        before = '3.6.2将操作指示卡放置在制备卡上。（图7）'
        sentence_guide = '本说明书中的所有图片均为示意图，图片内容可能与实物有细微差异，请以购买的产品为准。'
        detail, after = _build_sentence_review_detail(before, '', sentence_guide, 'style', '句式模板匹配')
        self.assertEqual(after, before)
        self.assertEqual(detail.get('suggested_text'), before)
        self.assertFalse(detail.get('has_change'))

    def test_document_feedback_stats_count_latest_record_per_document(self):
        now = datetime.utcnow()
        records = []

        first_doc_old = PolishFeedback(original_text='document:12:demo.docx', accuracy=1, processed_count=4, target='document_sentence_guide')
        first_doc_old.id = 1
        first_doc_old.created_at = now - timedelta(minutes=10)
        records.append(first_doc_old)

        first_doc_new = PolishFeedback(original_text='document:12:demo.docx', accuracy=3, processed_count=4, target='document_sentence_guide')
        first_doc_new.id = 2
        first_doc_new.created_at = now
        records.append(first_doc_new)

        second_doc = PolishFeedback(original_text='document:18:another.docx', accuracy=2, processed_count=5, target='document_sentence_guide')
        second_doc.id = 3
        second_doc.created_at = now - timedelta(minutes=2)
        records.append(second_doc)

        stats = _document_feedback_stats(records)
        self.assertEqual(stats['total_submissions'], 2)
        self.assertEqual(stats['average_accuracy'], 57.5)

    def test_build_document_feedback_record_key_prefers_document_id(self):
        self.assertEqual(_build_document_feedback_record_key(12, 'demo.docx'), 'document:12:demo.docx')
        self.assertEqual(_build_document_feedback_record_key(12, ''), 'document:12')
        self.assertEqual(_build_document_feedback_record_key(None, 'demo.docx'), 'demo.docx')

    def test_document_feedback_stats_merge_legacy_filename_with_document_key(self):
        now = datetime.utcnow()
        legacy = PolishFeedback(original_text='测试用说明书.docx', accuracy=1, processed_count=4, target='document_sentence_guide')
        legacy.id = 10
        legacy.created_at = now - timedelta(minutes=5)

        latest = PolishFeedback(original_text='document:88:测试用说明书.docx', accuracy=2, processed_count=4, target='document_sentence_guide')
        latest.id = 11
        latest.created_at = now

        stats = _document_feedback_stats([legacy, latest])
        self.assertEqual(stats['total_submissions'], 1)
        self.assertEqual(stats['average_accuracy'], 50.0)

    def test_ai_semantic_rerank_prefers_recommended_candidate(self):
        ranked = [
            {
                'template': '候选A',
                'candidate_text': '候选A',
                'match_level': 'L3',
                'guard_passed': False,
                'final_score': 0.91,
                'overall_score': 0.82,
            },
            {
                'template': '候选B',
                'candidate_text': '候选B',
                'match_level': 'L3',
                'guard_passed': False,
                'final_score': 0.83,
                'overall_score': 0.8,
            },
        ]

        from unittest.mock import patch

        with patch('app.api.polish._ai_template_rerank_cache', {
            'test-cache': {
                ('候选A', '候选A'): {'score': 62, 'recommended': False, 'reason': '信息不完整'},
                ('候选B', '候选B'): {'score': 95, 'recommended': True, 'reason': '语义完整'},
            }
        }), patch('app.api.polish.hashlib.sha1') as mock_sha1:
            mock_sha1.return_value.hexdigest.return_value = 'test-cache'
            reranked = _ai_semantic_rerank_candidates('原句', ranked)

        self.assertEqual(reranked[0]['template'], '候选B')
        self.assertTrue(reranked[0]['ai_semantic_recommended'])
        self.assertEqual(reranked[0]['ai_semantic_score'], 95)

    def test_ai_semantic_rerank_uses_top_two_when_only_one_high_score(self):
        fake_response = {
            'items': [
                {'index': 1, 'score': 96, 'recommended': True, 'reason': '更贴切'},
                {'index': 2, 'score': 12, 'recommended': False, 'reason': '不贴切'},
            ]
        }

        class FakeAIClient:
            has_any_client = True

            def chat(self, *_args, **_kwargs):
                return json.dumps(fake_response, ensure_ascii=False)

        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'app.utils.ai_client':
                return types.SimpleNamespace(ai_client=FakeAIClient())
            return original_import(name, globals, locals, fromlist, level)

        ranked = [
            {'template': '候选A', 'candidate_text': '候选A', 'final_score': 0.75, 'overall_score': 0.92, 'overall_percent': 92, 'guard_passed': False},
            {'template': '候选B', 'candidate_text': '候选B', 'final_score': 0.16, 'overall_score': 0.25, 'overall_percent': 25, 'guard_passed': False},
        ]
        try:
            builtins.__import__ = fake_import
            reranked = _ai_semantic_rerank_candidates('示例原句', ranked)
        finally:
            builtins.__import__ = original_import

        self.assertEqual(reranked[0]['template'], '候选A')
        self.assertEqual(reranked[0]['ai_semantic_score'], 96)
        self.assertEqual(reranked[1]['ai_semantic_score'], 12)

    def test_top_template_candidates_skips_rerank_for_high_score_candidate(self):
        sentence = '参数确认无误后点击运行按钮。'
        templates = ['参数确认无误后点击运行按钮。']

        from unittest.mock import patch

        with patch('app.api.polish._ai_semantic_rerank_candidates', side_effect=AssertionError('unexpected rerank call')):
            candidates = _top_template_candidates(sentence, templates, limit=5)

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].get('template'), '参数确认无误后点击运行按钮。')
        self.assertGreaterEqual(candidates[0].get('final_score', 0), 0.90)

    def test_bullet_only_difference_is_low_value(self):
        before = '*当运输条件、储存条件及使用方式都正确时，所有组分在有效期内均能保持完整活性。'
        after = '当运输条件、储存条件及使用方式都正确时，所有组分在有效期内均能保持完整活性。'
        self.assertTrue(_is_low_value_doc_change(before, after, 'style', '句式模板匹配'))

    def test_reapply_sentence_prefix_restores_step_number(self):
        before = '3.6.1从包装袋中取出样本制备卡、封闭液、加液装置和操作指示卡。（图6）'
        suggestion = '撕开真空包装袋，取出样本制备卡、封闭液管和加液装置，置于平整、干净的桌面。'
        result = _reapply_sentence_prefix(before, suggestion)
        self.assertTrue(result.startswith('3.6.1'))

    def test_reapply_sentence_prefix_keeps_notice_prefix(self):
        before = '注意：封闭液管经过真空处理，应缓缓旋转管盖打开，避免压力变化导致封闭液飞溅；同时打开时听到“砰”一声，说明气密性良好'
        suggestion = '封闭液管经过真空处理，应缓缓旋转管盖打开，避免压力变化导致封闭液飞溅。'
        result = _reapply_sentence_prefix(before, suggestion)
        self.assertTrue(result.startswith('注意：'))

    def test_sentence_review_detail_uses_prefixed_suggestion(self):
        before = '3.6.1从包装袋中取出样本制备卡、封闭液、加液装置和操作指示卡。（图6）'
        suggestion = '撕开真空包装袋，取出样本制备卡、封闭液管和加液装置，置于平整、干净的桌面。'
        detail, after = _build_sentence_review_detail(before, suggestion, '', 'style', '句式模板匹配')
        self.assertTrue(after.startswith('3.6.1'))
        self.assertTrue(detail.get('suggested_text', '').startswith('3.6.1'))

    def test_sentence_review_detail_drops_conflicting_critical_literal_suggestion(self):
        before = '3.2.1取出DNBelab-D4RS 样本制备套件 A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，输入制备卡信息。'
        suggestion = '3.2.1取出DNBelab-D4RS 样本制备套件 A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包安装的二维码，输入制备卡信息。'
        detail, after = _build_sentence_review_detail(before, suggestion, '', 'style', '句式模板匹配')
        self.assertEqual(after, before)
        self.assertEqual(detail.get('suggested_text'), before)
        self.assertFalse(detail.get('has_change'))

    def test_sentence_review_detail_drops_title_expansion_suggestion(self):
        before = '3.9 DNB取出'
        suggestion = '3.9 吸取 DNB 时会带出封闭液，封闭液为红色，DNB 为无色。'
        detail, after = _build_sentence_review_detail(before, suggestion, '', 'style', '句式模板匹配')
        self.assertEqual(after, before)
        self.assertEqual(detail.get('suggested_text'), before)
        self.assertEqual(detail.get('overall_percent'), 0)
        self.assertFalse(detail.get('has_change'))

    def test_sentence_review_detail_drops_title_punctuation_only_suggestion(self):
        before = '3.9 DNB取出'
        suggestion = '3.9 DNB取出。'
        detail, after = _build_sentence_review_detail(before, suggestion, '', 'style', '句式模板匹配')
        self.assertEqual(after, before)
        self.assertEqual(detail.get('suggested_text'), before)
        self.assertEqual(detail.get('overall_percent'), 0)
        self.assertFalse(detail.get('has_change'))

    def test_sentence_review_detail_drops_punctuation_only_suggestion_but_keeps_candidates(self):
        before = '注意：部分试剂会加多个孔位，按要求添加即可'
        suggestion = '注意：部分试剂会加多个孔位，按要求添加即可。'
        mocked_candidates = [{
            'candidate_text': '部分试剂需要加多个孔位，按照要求加到相应位置。',
            'template': '部分试剂需要加多个孔位，按照要求加到相应位置。',
            'overall_percent': 92,
            'overall_score': 0.92,
            'guard_passed': False,
        }]
        from unittest.mock import patch
        with patch('app.api.polish._filter_candidate_templates', return_value=['部分试剂需要加多个孔位，按照要求加到相应位置。']), patch('app.api.polish._top_template_candidates', return_value=mocked_candidates):
            detail, after = _build_sentence_review_detail(before, suggestion, 'mock-guide', 'style', '句式模板匹配')
        self.assertEqual(after, '注意：部分试剂需要加多个孔位，按照要求加到相应位置。')
        self.assertEqual(detail.get('overall_percent'), 92)
        self.assertTrue(detail.get('has_change'))
        self.assertTrue(detail.get('candidates'))
        self.assertIn('部分试剂需要加多个孔位', detail['candidates'][0].get('candidate_text', ''))

    def test_visible_change_entry_hides_bullet_only_difference(self):
        before = '*当运输条件、储存条件及使用方式都正确时，所有组分在有效期内均能保持完整活性。'
        after = '当运输条件、储存条件及使用方式都正确时，所有组分在有效期内均能保持完整活性。'
        self.assertIsNone(_build_visible_change_entry(1, before, after, 'ai', 'ai'))

    def test_visible_change_entry_restores_step_prefix(self):
        before = '3.6.1从包装袋中取出样本制备卡、封闭液、加液装置和操作指示卡。（图6）'
        after = '撕开真空包装袋，取出样本制备卡、封闭液管和加液装置，置于平整、干净的桌面。'
        entry = _build_visible_change_entry(1, before, after, 'ai', 'ai')
        self.assertIsNotNone(entry)
        self.assertTrue(entry['polished'].startswith('3.6.1'))

    def test_low_value_punctuation_change_is_hidden(self):
        before = '3.6.1从包装袋中取出样本制备卡、封闭液、加液装置和操作指示卡。（图6）'
        after = '3.6.1从包装袋中取出样本制备卡、封闭液、加液装置和操作指示卡。（图6）。'
        self.assertTrue(_is_low_value_doc_change(before, after, 'style', '基础规范化'))
        self.assertIsNone(_build_visible_change_entry(1, before, after, 'style', '基础规范化'))

    def test_sentence_review_detail_collapses_duplicate_terminal_punctuation(self):
        before = '3.8.7参数确认无误后点击界面上 按钮，点击run开始实验。'
        suggestion = '3.8.7参数确认无误后点击界面上 按钮，点击运行按钮，开始实验。。'
        detail, after = _build_sentence_review_detail(before, suggestion, '', 'style', '句式模板匹配')
        self.assertEqual(after, '3.8.7参数确认无误后点击界面上 按钮，点击运行按钮，开始实验。')
        self.assertEqual(detail.get('suggested_text'), '3.8.7参数确认无误后点击界面上 按钮，点击运行按钮，开始实验。')

    def test_normalize_doc_ai_line_collapses_duplicate_terminal_punctuation(self):
        before = '3.8.7参数确认无误后点击界面上 按钮，点击run开始实验。'
        ai_line = '3.8.7参数确认无误后点击界面上 按钮，点击运行按钮，开始实验。。'
        self.assertEqual(
            _normalize_doc_ai_line(before, ai_line),
            '3.8.7参数确认无误后点击界面上 按钮，点击运行按钮，开始实验。'
        )

    def test_normalize_doc_polished_text_collapses_duplicate_terminal_punctuation(self):
        before = '3.8.7参数确认无误后点击界面上 按钮，点击run开始实验。'
        polished = '参数确认无误后点击界面上 按钮，点击运行按钮，开始实验。。'
        self.assertEqual(
            _normalize_doc_polished_text(before, polished),
            '3.8.7参数确认无误后点击界面上 按钮，点击运行按钮，开始实验。'
        )

    def test_template_replace_guard_blocks_suite_letter_change(self):
        before = '3.2.1取出DNBelab-D4RS 样本制备套件 A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，输入制备卡信息。'
        after = '3.2.1取出DNBelab-D4RS样本制备套件B中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包安装的二维码，输入制备卡信息。'
        self.assertFalse(_template_replace_guard(before, after, 'L3', 0.9))

    def test_template_replace_guard_blocks_excessive_template_expansion(self):
        before = '根据选择的测序平台及对应样品的数据量需求，进行混样测序，并上机。'
        after = '根据选择的测序平台及对应样品的数据量需求，进行混样测序，为保证测序碱基平衡，本试剂盒已将PCRmix1-4及PCRmix5-8四个为一组预设为平衡碱基barcode组合，即可以单张D4芯片4样本，或者二张D4芯片8样本混样上机。'
        self.assertFalse(_template_replace_guard(before, after, 'L3', 0.95))

    def test_template_replace_guard_allows_close_structural_rewrite(self):
        before = '将样本制备卡置于载台上。'
        after = '将样本制备卡放置于载台上。'
        self.assertTrue(_template_replace_guard(before, after, 'L3', 0.95))

    def test_post_protect_blocks_critical_literal_change(self):
        before = '3.2.1取出DNBelab-D4RS 样本制备套件 A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，输入制备卡信息。'
        after = '3.2.1取出DNBelab-D4RS样本制备套件B中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包安装的二维码，输入制备卡信息。'
        result = instrument_polish_engine.post_protect(before, after)
        self.assertFalse(result['safe'])
        self.assertEqual(result['suggested'], before)
        self.assertIn('样本制备套件A', result['reason'])


if __name__ == '__main__':
    unittest.main()
