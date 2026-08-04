import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from alembic.util.exc import CommandError
from fastapi.testclient import TestClient


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


def test_vercel_returns_503_until_migrations_are_ready(monkeypatch, tmp_path):
    ready_file = tmp_path / "migrations-ready"
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_MIGRATION_READY_FILE", str(ready_file))

    from app.main import app

    client = TestClient(app)
    try:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "starting"}
        assert response.headers["Retry-After"] == "1"

        ready_file.touch()
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        client.close()


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


def test_vercel_entrypoint_starts_server_before_migrations_finish(tmp_path):
    call_log = tmp_path / "calls.log"
    ready_file = tmp_path / "migrations-ready"
    ready_file.write_text("stale", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    python = fake_bin / "python"
    python.write_text(
        "#!/bin/sh\n"
        "if [ -e \"$VERCEL_MIGRATION_READY_FILE\" ]; then "
        "state=present; else state=absent; fi\n"
        "printf 'python-start ready=%s state=%s\\n' "
        '"$VERCEL_MIGRATION_READY_FILE" "$state" >> "$CALL_LOG"\n'
        "sleep 1\n"
        "printf 'python-finish\\n' >> \"$CALL_LOG\"\n",
        encoding="utf-8",
    )
    python.chmod(0o755)

    uvicorn = fake_bin / "uvicorn"
    uvicorn.write_text(
        "#!/bin/sh\n"
        "printf 'uvicorn-start %s\\n' \"$*\" >> \"$CALL_LOG\"\n"
        "sleep 2\n",
        encoding="utf-8",
    )
    uvicorn.chmod(0o755)

    env = os.environ.copy()
    env["CALL_LOG"] = str(call_log).replace("\\", "/")
    env["VERCEL_MIGRATION_READY_FILE"] = str(ready_file).replace("\\", "/")
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

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert (
        f"python-start ready={str(ready_file).replace(chr(92), '/')} state=absent"
    ) in calls
    assert calls.index(
        "uvicorn-start app.main:app --host 0.0.0.0 --port 4317"
    ) < calls.index("python-finish")


def _load_vercel_migrations_module():
    module_path = PROJECT_ROOT / "vercel_migrations.py"
    spec = importlib.util.spec_from_file_location("vercel_migrations", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vercel_migration_runner_generates_then_applies(monkeypatch, tmp_path):
    module = _load_vercel_migrations_module()
    calls = []
    ready_file = tmp_path / "migrations-ready"
    monkeypatch.setenv("VERCEL_MIGRATION_READY_FILE", str(ready_file))

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
    assert ready_file.is_file()


def test_vercel_migration_runner_ignores_only_missing_revisions(
    monkeypatch, capsys, tmp_path
):
    module = _load_vercel_migrations_module()
    ready_file = tmp_path / "migrations-ready"
    monkeypatch.setenv("VERCEL_MIGRATION_READY_FILE", str(ready_file))

    def missing_revision(*args, **kwargs):
        raise CommandError("Can't locate revision identified by '985154533421'")

    monkeypatch.setattr(module.command, "revision", missing_revision)
    monkeypatch.setattr(module.command, "upgrade", missing_revision)

    module.main()

    assert capsys.readouterr().err.count(
        "WARNING: Ignoring missing Alembic revision and continuing."
    ) == 2
    assert ready_file.is_file()


def test_vercel_migration_runner_propagates_other_errors(monkeypatch, tmp_path):
    module = _load_vercel_migrations_module()
    ready_file = tmp_path / "migrations-ready"
    monkeypatch.setenv("VERCEL_MIGRATION_READY_FILE", str(ready_file))

    def connection_failure(*args, **kwargs):
        raise CommandError("connection refused")

    monkeypatch.setattr(module.command, "revision", connection_failure)

    with pytest.raises(CommandError, match="connection refused"):
        module.main()

    assert not ready_file.exists()
