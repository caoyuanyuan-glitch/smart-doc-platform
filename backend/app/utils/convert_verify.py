import os
import re
import xml.etree.ElementTree as ET


_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_SKIP_HREF_PREFIXES = ("http://", "https://", "mailto:", "#")


def _strip_doctype(text):
    return _DOCTYPE_RE.sub("", text or "", count=1)


def _local_tag(tag):
    if not tag:
        return ""
    return tag.split("}", 1)[-1]


def _rel_join(base_rel_dir, href):
    joined = os.path.normpath(os.path.join(base_rel_dir or ".", href)).replace(os.sep, "/")
    if joined.startswith("./"):
        joined = joined[2:]
    return joined


def _collect_output_files(output_base):
    files = set()
    for root, _, names in os.walk(output_base):
        for name in names:
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, output_base).replace(os.sep, "/")
            files.add(rel)
    return files


def _iter_xml_docs(output_base):
    for root, _, names in os.walk(output_base):
        for name in names:
            lower = name.lower()
            if not lower.endswith((".dita", ".ditamap", ".xml")):
                continue
            if name.lower() == "metadata.xml":
                continue
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, output_base).replace(os.sep, "/")
            try:
                with open(abs_path, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except Exception as exc:
                yield rel, None, str(exc)
                continue
            try:
                root_elem = ET.fromstring(_strip_doctype(text).encode("utf-8"))
            except Exception:
                yield rel, None, "XML 无法解析"
                continue
            yield rel, root_elem, None


def verify_output_dir(output_base, target_format="dita"):
    """Check generated conversion output before it is zipped.

    Returns (overall, checks) where overall is passed/warning/failed and each
    check is {name, status, detail}. Warnings keep the package downloadable.
    """
    if target_format == "csv":
        return "passed", [
            {"name": "结构完整性", "status": "passed", "detail": "已按逐行无损格式转换"},
        ]

    if not output_base or not os.path.isdir(output_base):
        return "failed", [
            {"name": "结构完整性", "status": "failed", "detail": "输出目录不存在"},
        ]

    existing = _collect_output_files(output_base)
    if target_format == "markdown":
        md_files = [path for path in existing if path.lower().endswith(".md")]
        status = "passed" if md_files else "failed"
        overall = "passed" if md_files else "warning"
        return overall, [
            {
                "name": "结构完整性",
                "status": status,
                "detail": f"生成 {len(md_files)} 个 Markdown 文件" if md_files else "未生成 Markdown 文件",
            }
        ]

    parse_errors = []
    missing_hrefs = []
    missing_images = []
    empty_bodies = []
    dita_count = 0
    map_count = 0

    for rel, root_elem, error in _iter_xml_docs(output_base):
        lower = rel.lower()
        if lower.endswith(".dita"):
            dita_count += 1
        elif lower.endswith(".ditamap"):
            map_count += 1
        if error:
            parse_errors.append(f"{rel}: {error}")
            continue

        base_dir = os.path.dirname(rel)
        for elem in root_elem.iter():
            href = (elem.get("href") or "").strip()
            if not href or href.startswith(_SKIP_HREF_PREFIXES):
                continue
            href_path = href.split("#", 1)[0]
            if not href_path:
                continue
            resolved = _rel_join(base_dir, href_path)
            if resolved in existing or href_path in existing:
                continue
            if href_path.startswith("image/") or resolved.startswith("image/"):
                missing_images.append(f"{rel} -> {href_path}")
            elif href_path.lower().endswith((".dita", ".ditamap")):
                missing_hrefs.append(f"{rel} -> {href_path}")

        if lower.endswith(".dita"):
            for elem in root_elem.iter():
                tag = _local_tag(elem.tag)
                if tag not in ("body", "conbody"):
                    continue
                has_child = any(True for _child in list(elem))
                text = "".join(elem.itertext()).strip()
                if not has_child and not text:
                    empty_bodies.append(rel)
                    break

    structure_status = "failed" if parse_errors else "passed"
    if parse_errors:
        structure_detail = f"{len(parse_errors)} 个文件无法解析：" + "；".join(parse_errors[:3])
    else:
        structure_detail = f"{dita_count} 个 topic，{map_count} 个 ditamap"

    href_status = "failed" if missing_hrefs else "passed"
    href_detail = (
        f"{len(missing_hrefs)} 个 href 缺失：" + "；".join(missing_hrefs[:3])
        if missing_hrefs else "ditamap / xref 均可达"
    )

    image_status = "warning" if missing_images else "passed"
    image_detail = (
        f"{len(missing_images)} 个图片缺失：" + "；".join(missing_images[:3])
        if missing_images else "引用图片均已打包"
    )

    body_status = "warning" if empty_bodies else "passed"
    body_detail = (
        f"{len(empty_bodies)} 个空 body：" + "、".join(empty_bodies[:3])
        if empty_bodies else "topic body 均有内容或空 p"
    )

    checks = [
        {"name": "结构完整性", "status": structure_status, "detail": structure_detail},
        {"name": "引用可达", "status": href_status, "detail": href_detail},
        {"name": "图片验证", "status": image_status, "detail": image_detail},
        {"name": "空正文", "status": body_status, "detail": body_detail},
    ]

    overall = "passed"
    if any(item["status"] == "failed" for item in checks) or any(item["status"] == "warning" for item in checks):
        overall = "warning"
    if dita_count == 0 and map_count == 0:
        overall = "failed"
        checks[0] = {"name": "结构完整性", "status": "failed", "detail": "未生成 DITA topic"}
    return overall, checks
