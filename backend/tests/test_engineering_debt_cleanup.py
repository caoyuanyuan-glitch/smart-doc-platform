"""工程债治理单测：全局计数器并发安全 + 三份工具函数归一（行为不变）。"""
import threading
import unittest

from app.review_engine import issue_position_utils as ipu
from app.review_engine import pipeline
from app.review_engine.cn_typo import _context as cn_context
from app.review_engine.learned_patch import _context as lp_context
from app.review_engine.unit_spacing import _context as us_context, _encode_position, _page_at


class EngineeringDebtTestCase(unittest.TestCase):
    def test_shared_utils_behavior(self):
        self.assertEqual(_encode_position(1, 2, area="甲"), '{"start": 1, "end": 2, "area": "甲"}')
        self.assertEqual(_page_at("a\fb", 5), 2)
        self.assertEqual(ipu.build_context("a   b", 0, 3), "a b")
        # 各模块保留原默认半径，但都委托同一实现
        self.assertEqual(us_context("a   b", 0, 3), cn_context("a   b", 0, 3))
        self.assertEqual(lp_context("a   b", 0, 3), ipu.build_context("a   b", 0, 3, radius=70))

    def test_drop_counter_concurrent(self):
        """并发 8 线程各记 100 次，drain 应拿到恰好 800，不串数据。"""
        pipeline.drain_pipeline_drop_reasons()  # 先清空
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            for _ in range(100):
                pipeline._log_pipeline_drop("test_reason", {"original_text": "x"})

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        result = pipeline.drain_pipeline_drop_reasons()
        self.assertEqual(result.get("test_reason"), 800)
        self.assertEqual(pipeline.drain_pipeline_drop_reasons(), {})  # 取出即清空


if __name__ == "__main__":
    unittest.main()
