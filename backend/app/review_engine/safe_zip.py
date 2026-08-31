"""Safe ZIP extraction for review-module DOCX comment injection."""

from __future__ import annotations

from pathlib import Path
import zipfile


class UnsafeZipError(ValueError):
    pass


DEFAULT_MAX_MEMBERS = 200
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 80 * 1024 * 1024
DEFAULT_MAX_RATIO = 100


def _is_unsafe_name(name: str) -> bool:
    raw = str(name or "").replace("\\", "/")
    if not raw or raw.endswith("/"):
        return False
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw or raw == "..":
        return True
    if ":" in raw.split("/")[0]:
        return True
    return False


def safe_extract_zip(
    zip_path,
    dest_dir,
    *,
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_ratio: int = DEFAULT_MAX_RATIO,
    allowed_prefixes: tuple[str, ...] | None = None,
) -> list[str]:
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as handle:
        infos = [info for info in handle.infolist() if not info.is_dir()]
        if len(infos) > max_members:
            raise UnsafeZipError(f"zip member count exceeds {max_members}")
        total = 0
        for info in infos:
            name = info.filename.replace("\\", "/")
            if _is_unsafe_name(name):
                raise UnsafeZipError(f"unsafe zip path: {info.filename}")
            if allowed_prefixes and not any(name == prefix or name.startswith(prefix) for prefix in allowed_prefixes):
                continue
            if info.file_size > max_file_bytes:
                raise UnsafeZipError(f"zip member too large: {info.filename}")
            compressed = info.compress_size or 1
            if info.file_size / compressed > max_ratio:
                raise UnsafeZipError(f"zip compression ratio too high: {info.filename}")
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest)):
                raise UnsafeZipError(f"zip path escapes destination: {info.filename}")
            if target.exists() and target.is_symlink():
                raise UnsafeZipError(f"refusing to extract over symlink: {info.filename}")
            total += info.file_size
            if total > max_total_bytes:
                raise UnsafeZipError("zip total uncompressed size exceeds limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(info, "r") as src, open(target, "wb") as out:
                remaining = info.file_size
                while remaining > 0:
                    chunk = src.read(min(65536, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
            if target.is_symlink():
                raise UnsafeZipError(f"extracted symlink is not allowed: {info.filename}")
            extracted.append(str(target))
    return extracted
