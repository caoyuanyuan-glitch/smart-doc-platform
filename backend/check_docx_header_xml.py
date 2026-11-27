"""Inspect raw header/footer XML text in the DOCX and compare with translated collection."""
import re
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch
from lxml import etree

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from app.api import translation as t

DOCX = Path(r"C:\MyFileAudit\shaolijuan\2026-09\H-020-001221-00 HIV-GenomePro 软件产品说明书_中文_RUO_SZ--test.docx")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

raw_texts = []
with zipfile.ZipFile(DOCX) as zf:
    names = [n for n in zf.namelist() if re.search(r"word/(header|footer)\d*\.xml$", n)]
    print(f"header/footer XML parts: {len(names)}")
    for name in names:
        root = etree.fromstring(zf.read(name))
        texts = [node.text or "" for node in root.iter(f"{W}t")]
        joined = "".join(texts).strip()
        if joined:
            raw_texts.append((name, joined))
            print(f"  {name}: {joined[:160]}")

collected = []


def fake_translate(texts, engine, model, source_lang, target_lang, db):
    collected.extend(texts)
    return list(texts)


with patch.object(t, "_translate_text_items", side_effect=fake_translate):
    t._translate_docx(str(DOCX), "hybrid", "kimi", "zh", "en", db=None)

normalized_collected = " ".join(collected)
print(f"\nraw header/footer parts with text: {len(raw_texts)}")
miss = []
for name, text in raw_texts:
    # split into words/segments for a rough containment check
    segments = [s.strip() for s in re.split(r"[\s，,。；;：:]+", text) if len(s.strip()) >= 3]
    found = sum(1 for s in segments if s in normalized_collected)
    print(f"{name}: segments={len(segments)}, found_in_translation={found}")
    if found < len(segments):
        miss.append(name)
print(f"parts not fully covered: {len(miss)}")
