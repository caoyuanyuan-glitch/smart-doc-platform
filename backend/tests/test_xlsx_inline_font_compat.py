import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.translation import (  # noqa: E402
    _load_xlsx_workbook_compat,
    _sanitize_xlsx_inline_font_xml,
)


class XlsxInlineFontCompatTest(unittest.TestCase):
    def test_sanitize_only_renames_name_inside_rpr(self):
        raw = (
            b'<sst><si><r><rPr><name val="Songti"/></rPr><t>abc</t></r></si>'
            b'<font><name val="Calibri"/></font></sst>'
        )
        changed, cleaned = _sanitize_xlsx_inline_font_xml(raw)
        self.assertTrue(changed)
        text = cleaned.decode("utf-8")
        self.assertIn('<rPr><rFont val="Songti"/></rPr>', text)
        self.assertIn('<font><name val="Calibri"/></font>', text)

    def test_load_workbook_with_wps_inline_font_names(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet["A1"] = "修订记录"
        buffer = io.BytesIO()
        workbook.save(buffer)

        patched = io.BytesIO()
        with zipfile.ZipFile(buffer, "r") as z_in, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as z_out:
            for info in z_in.infolist():
                data = z_in.read(info.filename)
                if info.filename == "xl/sharedStrings.xml":
                    data = data.replace(b"<rFont ", b"<name ")
                z_out.writestr(info, data)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wps_style.xlsx"
            path.write_bytes(patched.getvalue())
            loaded = _load_xlsx_workbook_compat(str(path))
            self.assertEqual(loaded.active["A1"].value, "修订记录")


if __name__ == "__main__":
    unittest.main()
