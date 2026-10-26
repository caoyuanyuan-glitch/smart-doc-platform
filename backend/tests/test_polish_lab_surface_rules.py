import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.polish_lab import (  # noqa: E402
    _apply_cat_terms,
    _classify_cat_surface_kind,
    _simple_match,
)


class PolishLabSurfaceRulesTest(unittest.TestCase):
    def test_apply_cat_terms_skips_already_standard_form(self):
        terms = {'仪器': '本仪器', '人身伤害': '人身安全'}
        text = '禁止在易燃易爆环境中使用本仪器。否则，可能导致仪器损坏，甚至造成人身伤害。'
        result = _apply_cat_terms(text, terms)
        self.assertNotIn('本本仪器', result)
        self.assertIn('使用本仪器', result)
        self.assertIn('本仪器损坏', result)
        self.assertIn('人身安全', result)

    def test_surface_kind_for_term_dict_is_term(self):
        original = '否则，可能导致仪器损坏，甚至造成人身伤害。'
        terms = {'仪器': '本仪器', '人身伤害': '人身安全'}
        revised = _apply_cat_terms(original, terms)
        self.assertEqual(_classify_cat_surface_kind(original, revised, term_dict=terms), 'term')

    def test_surface_kind_for_typo_dict_is_typo(self):
        original = '按装完成后开机。'
        typos = {'按装': '安装'}
        revised = _apply_cat_terms(original, typos)
        self.assertEqual(_classify_cat_surface_kind(original, revised, typo_dict=typos), 'typo')

    def test_simple_match_does_not_label_term_replace_as_typo(self):
        sentence = '否则，可能导致仪器损坏，甚至造成人身伤害。'
        terms = {'仪器': '本仪器', '人身伤害': '人身安全'}
        candidates = _simple_match(sentence, [], term_dict=terms)
        surface = [item for item in candidates if item.get('rule_source') == 'surface_rules']
        self.assertEqual(len(surface), 1)
        self.assertEqual(surface[0]['type'], 'term')
        self.assertNotIn('本本', surface[0].get('template_text') or '')

    def test_simple_match_skips_nested_standard_term(self):
        sentence = '禁止在易燃易爆环境中使用本仪器。'
        candidates = _simple_match(sentence, [], term_dict={'仪器': '本仪器'})
        surface = [item for item in candidates if item.get('rule_source') == 'surface_rules']
        self.assertEqual(surface, [])


if __name__ == '__main__':
    unittest.main()
