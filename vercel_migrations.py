import os
import sys
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError


MISSING_REVISION_MESSAGE = "Can't locate revision identified by"
DEFAULT_READY_FILE = "/tmp/vercel-migrations-ready"


def _run_alembic(operation: Callable[[], None]) -> None:
    try:
        operation()
    except CommandError as exc:
        if MISSING_REVISION_MESSAGE not in str(exc):
            raise
        print(f"FAILED: {exc}", file=sys.stderr, flush=True)
        print(
            "WARNING: Ignoring missing Alembic revision and continuing.",
            file=sys.stderr,
            flush=True,
        )


def mark_migrations_ready() -> None:
    ready_file = Path(
        os.getenv("VERCEL_MIGRATION_READY_FILE", DEFAULT_READY_FILE)
    )
    ready_file.touch()


def main() -> None:
    config = Config("alembic.ini")

    print("Generating new migrations from current models...", flush=True)
    _run_alembic(
        lambda: command.revision(config, autogenerate=True, message="auto")
    )

    print("Applying generated migrations...", flush=True)
    _run_alembic(lambda: command.upgrade(config, "head"))

    mark_migrations_ready()
    print("Database migrations are ready.", flush=True)


if __name__ == "__main__":
    main()
