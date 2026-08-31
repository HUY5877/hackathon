#!/usr/bin/env python
"""Generate and apply a reviewed Alembic migration on a developer machine."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="在本地生成并应用 Alembic 迁移文件",
    )
    parser.add_argument("message", help="迁移说明，例如 add_event_category")
    args = parser.parse_args()

    # Autogenerate compares models with the current database, so first bring the
    # developer database to the repository's current head.
    run_alembic("upgrade", "head")
    run_alembic("revision", "--autogenerate", "-m", args.message)
    run_alembic("upgrade", "head")

    print(
        "迁移已在本地生成并应用。请检查 alembic/versions 下的新文件，"
        "确认 upgrade/downgrade 后再提交到 Git。"
    )


if __name__ == "__main__":
    main()
