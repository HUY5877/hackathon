import os
from pathlib import Path
import shutil
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def test_vercel_entrypoint_runs_migrations_in_order_and_uses_vercel_port(tmp_path):
    call_log = tmp_path / "calls.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    for command in ("alembic", "uvicorn"):
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
        "alembic upgrade head",
        "alembic revision --autogenerate -m auto",
        "alembic upgrade head",
        "uvicorn app.main:app --host 0.0.0.0 --port 4317",
    ]


def _run_entrypoint_with_alembic_failure(tmp_path, error_message, exit_code):
    call_log = tmp_path / "calls.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    alembic = fake_bin / "alembic"
    alembic.write_text(
        "#!/bin/sh\n"
        "printf '%s %s\\n' \"$(basename \"$0\")\" \"$*\" >> \"$CALL_LOG\"\n"
        f"printf '%s\\n' \"{error_message}\" >&2\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    alembic.chmod(0o755)

    uvicorn = fake_bin / "uvicorn"
    uvicorn.write_text(
        '#!/bin/sh\nprintf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$CALL_LOG"\n',
        encoding="utf-8",
    )
    uvicorn.chmod(0o755)

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
    calls = call_log.read_text(encoding="utf-8").splitlines()
    return result, calls


def test_vercel_entrypoint_ignores_missing_revision_and_starts_server(tmp_path):
    result, calls = _run_entrypoint_with_alembic_failure(
        tmp_path,
        "Can't locate revision identified by '985154533421'",
        1,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr.count(
        "WARNING: Ignoring missing Alembic revision and continuing."
    ) == 3
    assert calls == [
        "alembic upgrade head",
        "alembic revision --autogenerate -m auto",
        "alembic upgrade head",
        "uvicorn app.main:app --host 0.0.0.0 --port 4317",
    ]


def test_vercel_entrypoint_stops_on_other_alembic_errors(tmp_path):
    result, calls = _run_entrypoint_with_alembic_failure(
        tmp_path,
        "connection refused",
        2,
    )

    assert result.returncode == 2
    assert "Ignoring missing Alembic revision" not in result.stderr
    assert calls == ["alembic upgrade head"]
