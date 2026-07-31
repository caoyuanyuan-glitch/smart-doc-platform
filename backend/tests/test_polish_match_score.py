import builtins
import json
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.api.polish import (  # noqa: E402
    _build_document_feedback_record_key,
    _document_feedback_stats,
    _filter_visible_doc_changes,
    _filter_candidate_templates,
    _top_template_candidates,
    _build_visible_change_entry,
    _cat_match_score,
    _filter_candidate_templates,
    _ai_semantic_rerank_candidates,
    _apply_constraint_polish,
    _build_sentence_review_detail,
    _template_replace_guard,
    _is_low_value_doc_change,
    _looks_like_title_or_noun_phrase,
    _preferred_entries_from_guide,
    _reapply_sentence_prefix,
    _should_emit_reference_review_change,
)
from app.utils.instrument_polisher import instrument_polish_engine  # noqa: E402
from app.models.polish_feedback import PolishFeedback  # noqa: E402


class PolishMatchScoreRegressionTest(unittest.TestCase):
    def test_bundled_structured_guide_contains_recent_pdf_templates(self):
        guide_path = BACKEND_ROOT / 'app' / 'static' / 'knowledge' / 'structured_sentence_guide_d4rs_operations.md'
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

    def test_bonus_signals_affect_ranking_but_not_display_percent(self):
        score = _cat_match_score(
            '在样本制备卡准备界面点击按钮，进入制备卡安装界面。',
            '点击按钮，进入制备卡安装界面。'
        )

        self.assertLess(score['overall_percent'], 100)
        self.assertNotEqual(score['raw_score'], score['display_raw_score'])
        self.assertGreater(score['ranking_score'], 0)
        self.assertGreater(score['term_anchor_score'], 0)

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

    def test_constraint_polish_keeps_predicate_wei_clause(self):
        sentence = '每个产物为一对barcode序列组合'
        self.assertEqual(_apply_constraint_polish(sentence), sentence)

    def test_constraint_polish_keeps_color_predicate_clause(self):
        sentence = '注意：吸取DNB时会带出封闭液，封闭液为红色，DNB为无色，目测无色液体体积在10µL-15µL左右则表示DNB完全吸出'
        self.assertEqual(_apply_constraint_polish(sentence), sentence)

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

    def test_clause_sentence_can_recall_split_candidate(self):
        guide_path = BACKEND_ROOT / 'app' / 'static' / 'knowledge' / 'structured_sentence_guide_d4rs_operations.md'
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
        guide_path = BACKEND_ROOT / 'app' / 'static' / 'knowledge' / 'structured_sentence_guide_d4rs_operations.md'
        guide_text = guide_path.read_text(encoding='utf-8')
        entries = _preferred_entries_from_guide(guide_text)
        sentence = '建议10分钟之内完成'

        from unittest.mock import patch
        with patch('app.api.polish._ai_semantic_rerank_candidates', side_effect=lambda _sentence, ranked: ranked):
            candidates = _top_template_candidates(sentence, entries, limit=5)

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].get('template'), '建议在 10 分钟内完成。')
        self.assertGreaterEqual(int(candidates[0].get('overall_percent', 0) or 0), 20)

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

    def test_template_replace_guard_blocks_suite_letter_change(self):
        before = '3.2.1取出DNBelab-D4RS 样本制备套件 A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，输入制备卡信息。'
        after = '3.2.1取出DNBelab-D4RS样本制备套件B中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包安装的二维码，输入制备卡信息。'
        self.assertFalse(_template_replace_guard(before, after, 'L3', 0.9))

    def test_post_protect_blocks_critical_literal_change(self):
        before = '3.2.1取出DNBelab-D4RS 样本制备套件 A中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包装上的二维码，输入制备卡信息。'
        after = '3.2.1取出DNBelab-D4RS样本制备套件B中的制备卡，利用DNBelab-D4RS样本制备系统上的扫码枪扫描制备卡包安装的二维码，输入制备卡信息。'
        result = instrument_polish_engine.post_protect(before, after)
        self.assertFalse(result['safe'])
        self.assertEqual(result['suggested'], before)
        self.assertIn('样本制备套件A', result['reason'])


if __name__ == '__main__':
    unittest.main()
