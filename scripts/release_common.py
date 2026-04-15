#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_root_package(root: Path | None = None) -> dict[str, Any]:
    root = repo_root() if root is None else root
    return json.loads((root / "package.json").read_text(encoding="utf-8"))


def load_platforms(root: Path | None = None) -> dict[str, dict[str, str]]:
    root = repo_root() if root is None else root
    return json.loads((root / "npm" / "platforms.json").read_text(encoding="utf-8"))


def load_pyproject_version(root: Path | None = None) -> str:
    root = repo_root() if root is None else root
    content = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^\[project\].*?^version = \"([^\"]+)\"", content)
    if not match:
        raise ValueError("missing [project].version in pyproject.toml")
    return match.group(1)


def project_version(root: Path | None = None) -> str:
    root = repo_root() if root is None else root
    package_version = str(load_root_package(root)["version"])
    pyproject_version = load_pyproject_version(root)
    if package_version != pyproject_version:
        raise ValueError(
            f"version mismatch: package.json={package_version} pyproject.toml={pyproject_version}"
        )
    return package_version
