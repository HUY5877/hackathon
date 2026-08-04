import os
import sys
from collections.abc import Callable
from pathlib import Path
from time import sleep

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy.exc import OperationalError


MISSING_REVISION_MESSAGE = "Can't locate revision identified by"
DEFAULT_READY_FILE = "/tmp/vercel-migrations-ready"


def _run_alembic(operation: Callable[[], None]) -> None:
    retries = max(int(os.getenv("VERCEL_MIGRATION_DB_RETRIES", "3")), 1)
    retry_delay = max(
        float(os.getenv("VERCEL_MIGRATION_DB_RETRY_DELAY", "1")),
        0,
    )

    for attempt in range(1, retries + 1):
        try:
            operation()
            return
        except OperationalError as exc:
            if attempt == retries:
                raise
            print(
                "WARNING: Database operation failed; "
                f"retrying ({attempt}/{retries}): {exc}",
                file=sys.stderr,
                flush=True,
            )
            sleep(retry_delay)
        except CommandError as exc:
            if MISSING_REVISION_MESSAGE not in str(exc):
                raise
            print(f"FAILED: {exc}", file=sys.stderr, flush=True)
            print(
                "WARNING: Ignoring missing Alembic revision and continuing.",
                file=sys.stderr,
                flush=True,
            )
            return


def mark_migrations_ready() -> None:
    ready_file = Path(
        os.getenv("VERCEL_MIGRATION_READY_FILE", DEFAULT_READY_FILE)
    )
    ready_file.touch()


def main() -> None:
    os.environ.setdefault(
        "PGCONNECT_TIMEOUT",
        os.getenv("VERCEL_DB_CONNECT_TIMEOUT", "5"),
    )
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
