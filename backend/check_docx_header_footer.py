"""Check whether _translate_docx collects header/footer paragraphs."""
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from docx import Document
from app.api import translation as t

DOCX = Path(r"C:\MyFileAudit\shaolijuan\2026-09\H-020-001221-00 HIV-GenomePro 软件产品说明书_中文_RUO_SZ--test.docx")

doc = Document(str(DOCX))
expected = []
for section in doc.sections:
    for name, container in (
        ("header", section.header),
        ("footer", section.footer),
        ("first_page_header", section.first_page_header),
        ("first_page_footer", section.first_page_footer),
        ("even_page_header", section.even_page_header),
        ("even_page_footer", section.even_page_footer),
    ):
        for para in getattr(container, "paragraphs", []):
            if para.text.strip():
                expected.append((name, para.text.strip()))

collected = []


def fake_translate(texts, engine, model, source_lang, target_lang, db):
    collected.extend(texts)
    return list(texts)


with patch.object(t, "_translate_text_items", side_effect=fake_translate):
    raw, originals, translated = t._translate_docx(
        str(DOCX), "hybrid", "kimi", "zh", "en", db=None
    )

print(f"docx sections: {len(doc.sections)}")
print(f"header/footer paragraphs with text (python-docx): {len(expected)}")
for name, text in expected[:12]:
    print(f"  [{name}] {text[:100]}")
print(f"paragraphs collected by _translate_docx: {len(collected)}")
matched = 0
for _, text in expected:
    if any(text == item.strip() for item in collected):
        matched += 1
print(f"header/footer paragraphs actually sent for translation: {matched}/{len(expected)}")
print(f"output bytes: {len(raw)}")
