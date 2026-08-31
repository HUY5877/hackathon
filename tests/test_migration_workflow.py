from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_migrations_have_one_linear_head() -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260828_cleaning_status"]
    assert script.get_revision("20260827_display_status").down_revision == (
        "73bef1ff85a5"
    )


def test_production_entrypoint_does_not_generate_migrations() -> None:
    entrypoint = (PROJECT_ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert "alembic revision" not in entrypoint
    assert entrypoint.count("alembic upgrade head") == 1
