import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.convert import (  # noqa: E402
    _append_root_container_xml,
    _should_emit_container_only,
)


class TitleOnlyTopicrefTest(unittest.TestCase):
    def test_empty_parent_with_children_is_container_only(self):
        self.assertTrue(_should_emit_container_only({
            "title": "进行前期准备",
            "content": "",
            "has_children": True,
            "level": 2,
        }))

    def test_parent_with_body_stays_real_topic(self):
        self.assertFalse(_should_emit_container_only({
            "title": "进行前期准备",
            "content": "先完成下列准备。",
            "has_children": True,
            "level": 2,
        }))

    def test_empty_leaf_stays_real_topic(self):
        self.assertFalse(_should_emit_container_only({
            "title": "准备耗材",
            "content": "",
            "has_children": False,
            "level": 3,
        }))

    def test_system_guide_empty_parent_stays_real_topic(self):
        self.assertFalse(_should_emit_container_only({
            "title": "进行前期准备",
            "content": "",
            "has_children": True,
            "level": 2,
        }, is_system_guide=True))

    def test_title_only_parent_emits_topicref_without_href(self):
        lines = []
        node = {
            "topic": {
                "title": "测序",
                "filename": "CTO041001.dita",
                "id": "CTO041001",
                "topic_kind": "chapter",
            },
            "children": [
                {
                    "topic": {
                        "title": "进行前期准备",
                        "filename": "",
                        "id": "",
                        "topic_kind": "task",
                        "is_container_only": True,
                    },
                    "children": [
                        {
                            "topic": {
                                "title": "准备耗材",
                                "filename": "DTO041003.dita",
                                "id": "DTO041003",
                                "topic_kind": "task",
                            },
                            "children": [],
                        }
                    ],
                }
            ],
        }
        _append_root_container_xml(
            lines,
            node,
            iter(range(1, 2)),
            iter(range(1, 10)),
            "  ",
            1,
            "20261106_090000",
            "zh-CN",
        )
        output = "\n".join(lines)
        self.assertIn('navtitle="进行前期准备"', output)
        self.assertNotRegex(output, r'navtitle="进行前期准备"[^>]*href=')
        self.assertNotRegex(output, r'navtitle="进行前期准备"[^>]*cms:template="sDitaTopic"')
        self.assertIn('href="DTO041003.dita"', output)
        self.assertIn('navtitle="准备耗材"', output)

    def test_empty_chapter_skips_chapter_topic_file(self):
        lines = []
        node = {
            "topic": {
                "title": "拆分Barcode",
                "filename": "",
                "id": "",
                "topic_kind": "chapter",
                "is_container_only": True,
            },
            "children": [
                {
                    "topic": {
                        "title": "步骤",
                        "filename": "DTO041002.dita",
                        "id": "DTO041002",
                        "topic_kind": "task",
                    },
                    "children": [],
                }
            ],
        }
        _append_root_container_xml(
            lines,
            node,
            iter(range(1, 2)),
            iter(range(1, 10)),
            "  ",
            1,
            "20261106_090000",
            "zh-CN",
        )
        output = "\n".join(lines)
        self.assertIn('<chapter navtitle="拆分Barcode"', output)
        self.assertNotIn('cms:template="chapterTopic"', output)
        self.assertIn('href="DTO041002.dita"', output)


if __name__ == "__main__":
    unittest.main()
