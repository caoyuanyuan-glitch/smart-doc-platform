"""Run the optimized AI+memory translation pipeline on user files with a deterministic Mock AI."""
import csv
import json
import re
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.api import translation as t

OUT_DIR = Path(r"C:\Users\shaolijuan\AppData\Local\Temp\hybrid-translation-output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FILES = [
    ("docx", Path(r"C:\MyFileAudit\shaolijuan\2026-09\H-020-001221-00 HIV-GenomePro 软件产品说明书_中文_RUO_SZ--test.docx"), t._translate_docx),
    ("idml", Path(r"C:\MyFileAudit\shaolijuan\2026-09\H-020-001221-00 HIV-GenomePro 软件产品说明书_中文_RUO_SZ--test.idml"), t._translate_idml),
    ("xlsx", Path(r"C:\MyFileAudit\shaolijuan\2026-09\D22P0007-01-5-0009 Dolphin产品主文档清单.xlsx"), t._translate_xlsx),
]
TM_FILES = [
    Path(r"C:\MyFileAudit\shaolijuan\2026-10\全领域总TM-20261105.csv"),
    Path(r"C:\MyFileAudit\shaolijuan\2026-01\T1_T7_CoolMPS_DMR_DHF.csv"),
]


def normalize_tm_csv(src: Path, dst: Path):
    encoding = t._detect_text_encoding(str(src))
    with open(src, "r", encoding=encoding, errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))
    with open(dst, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["zh-CN", "en-US"])
        for row in rows:
            if len(row) < 2:
                continue
            source = (row[0] or "").strip().strip('"')
            translated = (row[1] or "").strip().strip('"')
            if not source or not translated:
                continue
            writer.writerow([source, translated])
    return dst


def sanitize_xlsx(src: Path, dst: Path):
    """Fix WPS-style <name val=.../> font tags that openpyxl cannot parse."""
    import zipfile

    with zipfile.ZipFile(src, "r") as z_in, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z_out:
        for info in z_in.infolist():
            raw = z_in.read(info.filename)
            if info.filename in ("xl/sharedStrings.xml", "xl/styles.xml"):
                text = raw.decode("utf-8", errors="replace")
                text = text.replace("<name val=", "<rFont val=")
                raw = text.encode("utf-8")
            z_out.writestr(info, raw)
    return dst


def mock_one(text: str) -> str:
    ascii_only = re.sub(r"[^\x00-\x7F]", lambda m: f"U{ord(m.group()):04X}", text or "")
    return f"[mock-en] {ascii_only}"


def mock_translate_with_ai(text, model, source_lang, target_lang, batch_separator=None, **kwargs):
    if batch_separator and batch_separator in (text or ""):
        return batch_separator.join(mock_one(part) for part in text.split(batch_separator))
    return mock_one(text)


def main():
    normalized_tm = []
    for index, path in enumerate(TM_FILES):
        target = OUT_DIR / f"tm_{index}_normalized.csv"
        normalize_tm_csv(path, target)
        normalized_tm.append(target)

    entries = []
    for path in normalized_tm:
        loaded = t._load_memory_file_entries(str(path), "csv")
        print(f"TM loaded: {path.name} -> {len(loaded)} entries")
        entries.extend(loaded)
    seen = set()
    unique_entries = []
    for entry in entries:
        key = (entry.get("source_text"), entry.get("translated_text"))
        if key in seen or not key[0] or not key[1]:
            continue
        seen.add(key)
        unique_entries.append(entry)
    print(f"TM unique entries: {len(unique_entries)}")
    bundle = t._build_memory_candidate_bundle(unique_entries)

    t._get_memory_candidate_bundle = lambda *args, **kwargs: bundle
    t.translate_with_ai = mock_translate_with_ai

    results = []
    for ext, path, func in FILES:
        input_path = path
        if ext == "xlsx":
            input_path = sanitize_xlsx(path, OUT_DIR / "input_xlsx_sanitized.xlsx")
        t._reset_translation_usage_stats()
        t._set_memory_bank("user-test-bank")
        t._set_memory_file_ids(memory_file_ids=[1, 2])
        started = time.perf_counter()
        raw, originals, translated = func(str(input_path), "hybrid", "mock", "zh", "en", db=None)
        elapsed = time.perf_counter() - started
        stats = t._get_translation_usage_stats()
        out_path = OUT_DIR / f"translated_{path.stem.replace(' ', '_')}{path.suffix}"
        out_path.write_bytes(raw)
        results.append({
            "file": path.name,
            "extension": ext,
            "elapsed_seconds": round(elapsed, 3),
            "ai_word_count": stats["ai_word_count"],
            "memory_word_count": stats["memory_word_count"],
            "source_word_count": stats["ai_word_count"] + stats["memory_word_count"],
            "unit_count": len(originals),
            "output_file": str(out_path),
            "output_bytes": len(raw),
        })
        print(json.dumps(results[-1], ensure_ascii=False))

    summary = OUT_DIR / "translation_stats.json"
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SUMMARY={summary}")


if __name__ == "__main__":
    main()
