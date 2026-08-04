import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from alembic.util.exc import CommandError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_vercel_compute_runs_close_to_database():
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["regions"] == ["hkg1"]


def test_vercel_skips_redundant_startup_database_probe(monkeypatch):
    from app.main import should_probe_database_on_startup

    monkeypatch.setenv("VERCEL", "1")
    assert should_probe_database_on_startup() is False

    monkeypatch.delenv("VERCEL")
    assert should_probe_database_on_startup() is True


def _find_posix_shell() -> str:
    shell = shutil.which("sh")
    if shell:
        return shell

    git = shutil.which("git")
    if git:
        bundled_shell = Path(git).resolve().parents[1] / "bin" / "sh.exe"
        if bundled_shell.exists():
            return str(bundled_shell)

    raise RuntimeError("A POSIX shell is required to test the Vercel entrypoint")


def test_vercel_entrypoint_generates_then_applies_migrations_and_uses_vercel_port(
    tmp_path,
):
    call_log = tmp_path / "calls.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    for command in ("python", "uvicorn"):
        executable = fake_bin / command
        executable.write_text(
            '#!/bin/sh\nprintf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$CALL_LOG"\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)

    env = os.environ.copy()
    env["CALL_LOG"] = str(call_log).replace("\\", "/")
    env["PORT"] = "4317"
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    result = subprocess.run(
        [_find_posix_shell(), str(PROJECT_ROOT / "entrypoint.vercel.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr

    assert call_log.read_text(encoding="utf-8").splitlines() == [
        "python vercel_migrations.py",
        "uvicorn app.main:app --host 0.0.0.0 --port 4317",
    ]


def _load_vercel_migrations_module():
    module_path = PROJECT_ROOT / "vercel_migrations.py"
    spec = importlib.util.spec_from_file_location("vercel_migrations", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vercel_migration_runner_generates_then_applies(monkeypatch):
    module = _load_vercel_migrations_module()
    calls = []

    monkeypatch.setattr(
        module.command,
        "revision",
        lambda config, **kwargs: calls.append(("revision", kwargs)),
    )
    monkeypatch.setattr(
        module.command,
        "upgrade",
        lambda config, revision: calls.append(("upgrade", revision)),
    )

    module.main()

    assert calls == [
        ("revision", {"autogenerate": True, "message": "auto"}),
        ("upgrade", "head"),
    ]


def test_vercel_migration_runner_ignores_only_missing_revisions(
    monkeypatch, capsys
):
    module = _load_vercel_migrations_module()

    def missing_revision(*args, **kwargs):
        raise CommandError("Can't locate revision identified by '985154533421'")

    monkeypatch.setattr(module.command, "revision", missing_revision)
    monkeypatch.setattr(module.command, "upgrade", missing_revision)

    module.main()

    assert capsys.readouterr().err.count(
        "WARNING: Ignoring missing Alembic revision and continuing."
    ) == 2


def test_vercel_migration_runner_propagates_other_errors(monkeypatch):
    module = _load_vercel_migrations_module()

    def connection_failure(*args, **kwargs):
        raise CommandError("connection refused")

    monkeypatch.setattr(module.command, "revision", connection_failure)

    with pytest.raises(CommandError, match="connection refused"):
        module.main()
