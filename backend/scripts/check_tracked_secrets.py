#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail if git-tracked env files contain plaintext secret assignments."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND_DIR.parent
_SECRET_KEY = re.compile(
    r"(^|_)(API_KEY|SECRET_KEY|SECRET|PASSWORD|ACCESS_TOKEN|REFRESH_TOKEN)(_FILE)?$"
)
_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ASSIGN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _placeholder(value: str) -> bool:
    text = value.strip().strip('"').strip("'")
    if not text:
        return True
    lowered = text.lower()
    if any(mark in lowered for mark in ("your-", "changeme", "placeholder", "example", "dummy")):
        return True
    if text.startswith("${") or text.startswith("<"):
        return True
    return False


def _is_env_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    lowered = name.lower()
    if ".example" in lowered or ".sample" in lowered:
        return False
    return name == "runtime.env" or name.startswith(".env") or name.endswith(".env") or ".env." in name


def _tracked_env_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # git 配置不可读 / 不在仓库内 / 无权限 —— 都归到这里。
        # 注意：不能静默返回空列表，否则「扫不到文件」会被误读成「没有密钥」。
        raise SystemExit(
            "check_tracked_secrets: git ls-files 执行失败"
            f"（cwd={_ROOT}, rc={proc.returncode}）：{proc.stderr.strip()}"
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip() and _is_env_file(line.strip())]


def main() -> int:
    offenders = []
    for rel in _tracked_env_files():
        path = _ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, raw in enumerate(text.splitlines(), 1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _ASSIGN.match(stripped)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            if not _ENV_KEY.match(key) or not _SECRET_KEY.search(key):
                continue
            if _placeholder(value):
                continue
            offenders.append(f"{rel}:{lineno}:{key}")
    if offenders:
        print("tracked env files contain secret-like assignments:", file=sys.stderr)
        for item in offenders:
            print(item, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
