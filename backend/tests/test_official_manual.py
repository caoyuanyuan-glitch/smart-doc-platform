import unittest

from app.utils.official_manual import (
    dedup_latest_by_fcode,
    extract_search_keyword,
    extract_search_keywords,
    filter_manuals_by_keyword,
    filter_manuals_by_lang,
    keyword_variants,
    needs_user_choice,
    needs_user_choice_for_keywords,
    normalize_official_item,
    normalize_site,
    official_site,
    OfficialSearchError,
    pick_from_candidates,
    rank_manuals,
    score_manual,
    search_official_manuals,
    select_manuals,
    select_manuals_for_keywords,
)


class OfficialManualUtilTest(unittest.TestCase):
    def test_extract_prefers_product_field(self):
        self.assertEqual(
            extract_search_keyword("开机前要检查什么", "DNBSEQ-T1+"),
            "DNBSEQ-T1+",
        )

    def test_extract_model_from_question(self):
        self.assertEqual(
            extract_search_keyword("T1+ 开机前要检查哪些项目？"),
            "T1+",
        )

    def test_extract_catalog_number(self):
        self.assertEqual(
            extract_search_keyword("货号 940-003016-00 对应哪本说明书"),
            "940-003016-00",
        )

    def test_rank_prefers_chinese_full_manual(self):
        items = [
            {
                "id": 1,
                "fcode": "H-1",
                "title": "DNBSEQ-T1+ User Manual_English_RUO",
                "updatetime": 200,
            },
            {
                "id": 2,
                "fcode": "H-2",
                "title": "H-020 DNBSEQ-T1+RS 基因测序仪系统操作指南_中文_RUO",
                "updatetime": 100,
            },
            {
                "id": 3,
                "fcode": "H-3",
                "title": "DNBSEQ-T1+RS 基因测序仪快速操作指南_中文_RUO",
                "updatetime": 300,
            },
        ]
        ranked = rank_manuals(items, "T1+ 开机流程是什么", "T1+")
        self.assertIn("系统操作指南", ranked[0]["title"])
        self.assertIn("中文", ranked[0]["title"])

    def test_dedup_keeps_latest_fcode(self):
        items = [
            {"id": 1, "fcode": "H-020-001077-00", "title": "old", "updatetime": 10},
            {"id": 2, "fcode": "H-020-001077-00", "title": "new", "updatetime": 99},
        ]
        out = dedup_latest_by_fcode(items)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "new")

    def test_select_defaults_to_one(self):
        ranked = [
            {"id": 1, "fcode": "A", "title": "a", "_score": 10},
            {"id": 2, "fcode": "B", "title": "b", "_score": 9},
        ]
        selected = select_manuals(ranked, "T1+ 开机流程", max_count=1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["id"], 1)

    def test_pick_from_candidates_by_official_id(self):
        rows = [{"official_id": 1489, "title": "t1"}, {"id": 1473, "title": "quick"}]
        picked = pick_from_candidates(rows, [1489])
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0]["title"], "t1")

    def test_variants_hyphenate_spaced_model(self):
        variants = keyword_variants("siro 16")
        self.assertEqual(variants[0], "siro-16")
        self.assertIn("siro 16", variants)

    def test_extract_spaced_model_from_question(self):
        self.assertEqual(extract_search_keyword("siro 16 的开机流程"), "siro 16")

    def test_score_fuzzy_matches_hyphenated_title(self):
        item = {
            "title": "H-020-001122-00 GenSIRO-16RS 全自动测序文库制备系统产品说明书_中文_RUO",
            "artno": "",
            "updatetime": 1,
        }
        spaced = score_manual(item, "开机流程", "siro 16", "zh")
        hyphen = score_manual(item, "开机流程", "siro-16", "zh")
        miss = score_manual(item, "开机流程", "t1+", "zh")
        self.assertGreaterEqual(spaced, 20)
        self.assertGreaterEqual(hyphen, 20)
        self.assertLess(miss, spaced)

    def test_search_retries_hyphen_variant(self):
        class FakeResp:
            def __init__(self, keyword):
                self.keyword = keyword

            def raise_for_status(self):
                return None

            def json(self):
                if self.keyword.lower() == "siro-16":
                    return {
                        "status": 1,
                        "data": {
                            "data": [{"id": 88, "title": "GenSIRO-16RS 产品说明书_中文"}]
                        },
                    }
                return {"status": 1, "data": {"data": []}}

        class FakeClient:
            def __init__(self):
                self.seen = []

            def post(self, url, json=None, headers=None):
                kw = json["keyword"]
                self.seen.append(kw)
                return FakeResp(kw)

        client = FakeClient()
        rows = search_official_manuals("siro 16", client=client)
        self.assertEqual(client.seen[0], "siro-16")
        self.assertEqual(len(rows), 1)
        self.assertIn("SIRO-16", rows[0]["title"])

    def test_filter_drops_unrelated_official_hits(self):
        items = [
            {"title": "MGAP 微生物组装溯源软件产品说明书_中文", "artno": "970-000109-00", "fcode": "H-1"},
            {"title": "PFI & PFI Pro 产品说明书_中文", "artno": "900-000392-00", "fcode": "H-2"},
        ]
        kept = filter_manuals_by_keyword(items, "MGAP")
        self.assertEqual(len(kept), 1)
        self.assertIn("MGAP", kept[0]["title"])

    def test_same_artno_does_not_need_choice(self):
        items = [
            {"title": "MGAP 微生物组装溯源软件产品说明书_中文", "artno": "970-000109-00", "fcode": "H-1"},
            {"title": "MGAP Microbial Genome Analysis Pipeline Software User Manual_English", "artno": "970-000109-00", "fcode": "H-2"},
        ]
        self.assertFalse(needs_user_choice(items, "MGAP"))

    def test_different_products_need_choice(self):
        items = [
            {"title": "MGAP 微生物组装溯源软件产品说明书_中文", "artno": "970-000109-00", "fcode": "H-1"},
            {"title": "MGAP Hardware 产品说明书_中文", "artno": "111-000000-00", "fcode": "H-3"},
        ]
        self.assertTrue(needs_user_choice(items, "MGAP"))

    def test_extract_multiple_products(self):
        self.assertEqual(
            extract_search_keywords("开机流程", "T1+, T7"),
            ["T1+", "T7"],
        )
        self.assertEqual(
            extract_search_keywords("开机流程", "T1+ T7"),
            ["T1+", "T7"],
        )

    def test_select_one_manual_per_keyword(self):
        ranked = [
            {"id": 1, "fcode": "A", "title": "T1+ 系统操作指南", "artno": "940-1", "_score": 10},
            {"id": 2, "fcode": "B", "title": "T7 系统操作指南", "artno": "940-2", "_score": 9},
        ]
        selected = select_manuals_for_keywords(ranked, "开机流程", ["T1+", "T7"])
        self.assertEqual({item["id"] for item in selected}, {1, 2})

    def test_multi_keyword_skips_choice_when_each_unique(self):
        items = [
            {"title": "T1+ 系统操作指南", "artno": "940-1", "fcode": "H-1"},
            {"title": "T7 系统操作指南", "artno": "940-2", "fcode": "H-2"},
        ]
        self.assertFalse(needs_user_choice_for_keywords(items, ["T1+", "T7"]))

    def test_multi_keyword_skips_choice_when_each_has_variants(self):
        items = [
            {"title": "T7+ 系统操作指南", "artno": "1", "fcode": "H-1"},
            {"title": "T7+ 快速操作指南", "artno": "2", "fcode": "H-2"},
            {"title": "T1+ 系统操作指南", "artno": "3", "fcode": "H-3"},
            {"title": "G99 系统操作指南", "artno": "4", "fcode": "H-4"},
        ]
        self.assertFalse(needs_user_choice_for_keywords(items, ["T7+", "T1+", "G99"]))

    def test_normalize_site(self):
        self.assertEqual(normalize_site("en"), "en")
        self.assertEqual(normalize_site("english"), "en")
        self.assertEqual(normalize_site("zh"), "zh")
        self.assertEqual(normalize_site(""), "zh")

    def test_english_site_points_to_global(self):
        cfg = official_site("en")
        self.assertEqual(cfg["base"], "https://global-mgitech.com")
        self.assertEqual(cfg["library_url"], "https://global-mgitech.com/resources/manual-library/")
        self.assertIn("/wp-json/cua/v1/search", cfg["search_url"])
        zh = official_site("zh")
        self.assertEqual(zh["library_url"], "https://mgi-tech.com/manual")
        self.assertIn("/index/index/manualSeaList", zh["search_url"])

    def test_normalize_english_item(self):
        row = normalize_official_item({
            "id": 71980,
            "title": "legacy",
            "file_url": "https://global-mgitech.com/wp-content/uploads/Documents/t7.pdf",
            "cua_title": "DNBSEQ-T7+RS Genetic Sequencer System Guide_English_RUO_WH",
            "cua_fcode": "H-020-001143-00",
            "cua_docuver": "6.0",
            "cua_effdate": "2026-09-30",
            "cua_softversion": "V0.2.0.1131",
            "cua_pline": "Instrument equipment",
        }, "en")
        self.assertIn("System Guide", row["title"])
        self.assertEqual(row["fcode"], "H-020-001143-00")
        self.assertTrue(row["files"].startswith("https://global-mgitech.com/"))
        self.assertEqual(row["downloadurl"], row["files"])

    def test_rank_prefers_english_when_lang_en(self):
        items = [
            {
                "id": 1,
                "fcode": "H-1",
                "title": "DNBSEQ-T1+ User Manual_English_RUO",
                "updatetime": 100,
            },
            {
                "id": 2,
                "fcode": "H-2",
                "title": "H-020 DNBSEQ-T1+RS 基因测序仪系统操作指南_中文_RUO",
                "updatetime": 200,
            },
        ]
        ranked = rank_manuals(items, "T1+ 开机流程是什么", "T1+", lang="en")
        self.assertIn("English", ranked[0]["title"])

    def test_filter_drops_opposite_language(self):
        items = [
            {"title": "DNBSEQ-T1+ User Manual_English_RUO", "id": 1},
            {"title": "H-020 DNBSEQ-T1+RS 基因测序仪系统操作指南_中文_RUO", "id": 2},
        ]
        en_only = filter_manuals_by_lang(items, "en")
        zh_only = filter_manuals_by_lang(items, "zh")
        self.assertEqual([i["id"] for i in en_only], [1])
        self.assertEqual([i["id"] for i in zh_only], [2])

    def test_english_same_product_does_not_need_choice(self):
        items = [
            {
                "id": 1,
                "fcode": "H-020-001078-00",
                "title": "H-020-001078-00 DNBSEQ-T1+RS Genetic Sequencer Quick Start Guide_English_RUO_SZ",
            },
            {
                "id": 2,
                "fcode": "H-020-001104-00",
                "title": "H-020-001104-00 DNBSEQ-T1+RS Genetic Sequencer System Guide_English_RUO_SZ",
            },
        ]
        ranked = rank_manuals(items, "T1+ power on checks", "T1+", lang="en")
        self.assertFalse(needs_user_choice(ranked, "T1+"))
        self.assertIn("System Guide", select_manuals(ranked, "T1+ power on checks")[0]["title"])

    def test_search_english_site_uses_wp_endpoint(self):
        class FakeResp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "status": 1,
                    "items": [{
                        "id": 71980,
                        "cua_title": "DNBSEQ-T7+RS Genetic Sequencer System Guide_English_RUO_WH",
                        "file_url": "https://global-mgitech.com/wp-content/uploads/Documents/t7.pdf",
                        "cua_fcode": "H-020-001143-00",
                        "cua_docuver": "6.0",
                        "cua_effdate": "2026-09-30",
                    }],
                }

        class FakeClient:
            def __init__(self):
                self.seen = []

            def get(self, url, params=None, headers=None):
                self.seen.append((url, dict(params or {})))
                return FakeResp()

            def post(self, *args, **kwargs):
                raise AssertionError("english site should GET")

        client = FakeClient()
        rows = search_official_manuals("T7+", client=client, site="en")
        self.assertTrue(client.seen)
        self.assertIn("/wp-json/cua/v1/search", client.seen[0][0])
        self.assertEqual(client.seen[0][1].get("q"), "T7+")
        self.assertEqual(len(rows), 1)
        self.assertIn("System Guide", rows[0]["title"])
        self.assertTrue(str(rows[0]["files"]).startswith("https://"))

    def test_search_raises_when_library_unreachable(self):
        class FakeClient:
            def get(self, *args, **kwargs):
                raise ConnectionError("tls timeout")

            def post(self, *args, **kwargs):
                raise AssertionError("english site should GET")

        with self.assertRaises(OfficialSearchError) as ctx:
            search_official_manuals("T7+", client=FakeClient(), site="en")
        self.assertEqual(ctx.exception.library_url, "https://global-mgitech.com/resources/manual-library/")


if __name__ == "__main__":
    unittest.main()
