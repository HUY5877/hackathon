import sys
from collections.abc import Callable

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError


MISSING_REVISION_MESSAGE = "Can't locate revision identified by"


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


def main() -> None:
    config = Config("alembic.ini")

    print("Generating new migrations from current models...", flush=True)
    _run_alembic(
        lambda: command.revision(config, autogenerate=True, message="auto")
    )

    print("Applying generated migrations...", flush=True)
    _run_alembic(lambda: command.upgrade(config, "head"))


if __name__ == "__main__":
    main()
