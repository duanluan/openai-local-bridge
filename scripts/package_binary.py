#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def archive_name(target: str) -> str:
    return f"{target}.zip" if "windows" in target else f"{target}.tar.gz"


def main() -> int:
    args = parse_args()
    binary = Path(args.binary).resolve()
    output_dir = Path(args.output_dir).resolve()
    repo_root = Path(__file__).resolve().parents[1]

    output_dir.mkdir(parents=True, exist_ok=True)
    package_root = Path(args.target)
    archive_path = output_dir / archive_name(args.target)

    with tempfile.TemporaryDirectory() as tmp:
        staging_root = Path(tmp) / package_root
        staging_root.mkdir(parents=True, exist_ok=True)

        shutil.copy2(binary, staging_root / binary.name)
        shutil.copy2(repo_root / "README.md", staging_root / "README.md")
        shutil.copy2(repo_root / "README_CN.md", staging_root / "README_CN.md")

        if archive_path.suffix == ".zip":
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as zip_file:
                for file in staging_root.iterdir():
                    zip_file.write(file, arcname=f"{package_root}/{file.name}")
        else:
            with tarfile.open(archive_path, "w:gz") as tar_file:
                tar_file.add(staging_root, arcname=package_root)

    print(archive_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
