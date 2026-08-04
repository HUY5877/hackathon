# Vercel Background Migrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Vercel container listen on `$PORT` before synchronizing the database, while refusing business traffic until migrations finish.

**Architecture:** The shell entrypoint starts `vercel_migrations.py` in the background and immediately execs Uvicorn. The migration runner creates a readiness file only after `revision --autogenerate` and `upgrade head` finish; an HTTP middleware conditionally waits for that file so Vercel keeps the first invocation active, then returns `503` only if the wait times out.

**Tech Stack:** POSIX shell, Python 3.11, FastAPI/Starlette, Alembic, pytest

## Global Constraints

- Work only on `dev-vercel`.
- Preserve migration order as `revision --autogenerate` then `upgrade head`.
- Continue ignoring only `Can't locate revision identified by`; propagate every other Alembic error.
- Do not modify or commit existing untracked `alembic/versions/*.py` files.
- Do not modify the normal Docker Compose entrypoint.

---

### Task 1: Start Uvicorn Before Migrations Finish

**Files:**
- Modify: `entrypoint.vercel.sh`
- Modify: `tests/test_vercel_deployment.py`

**Interfaces:**
- Consumes: `VERCEL_MIGRATION_READY_FILE`, defaulting to `/tmp/vercel-migrations-ready`
- Produces: a background `python vercel_migrations.py` process and immediate Uvicorn execution

- [ ] **Step 1: Write the failing entrypoint concurrency test**

Create fake `python` and `uvicorn` executables that log start/finish events and sleep long enough to make ordering observable. Assert `uvicorn-start` appears before `python-finish` and the ready-file environment variable reaches the migration process.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_vercel_deployment.py::test_vercel_entrypoint_starts_server_before_migrations_finish -q`

Expected: FAIL because the current entrypoint waits for Python to finish before launching Uvicorn.

- [ ] **Step 3: Implement background startup**

Use this behavior in `entrypoint.vercel.sh`:

```sh
export VERCEL_MIGRATION_READY_FILE="${VERCEL_MIGRATION_READY_FILE:-/tmp/vercel-migrations-ready}"
rm -f "$VERCEL_MIGRATION_READY_FILE"
python vercel_migrations.py &
echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-80}"
```

- [ ] **Step 4: Run the targeted test and confirm it passes**

Run: `python -m pytest tests/test_vercel_deployment.py::test_vercel_entrypoint_starts_server_before_migrations_finish -q`

Expected: PASS.

### Task 2: Publish Migration Readiness Only on Success

**Files:**
- Modify: `vercel_migrations.py`
- Modify: `tests/test_vercel_deployment.py`

**Interfaces:**
- Consumes: `VERCEL_MIGRATION_READY_FILE: str`
- Produces: `mark_migrations_ready() -> None`, creating the configured file after both Alembic operations

- [ ] **Step 1: Write failing readiness-file tests**

Assert that `main()` creates the configured marker after successful/ignored-missing-revision operations, and that a generic `CommandError` leaves the marker absent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_vercel_deployment.py -k "migration_runner" -q`

Expected: FAIL because the runner does not create a readiness file.

- [ ] **Step 3: Implement the readiness marker**

Add:

```python
def mark_migrations_ready() -> None:
    ready_file = Path(
        os.getenv("VERCEL_MIGRATION_READY_FILE", "/tmp/vercel-migrations-ready")
    )
    ready_file.touch()
```

Call it only after `command.revision(...)` and `command.upgrade(...)` return or are accepted as missing-revision errors.

- [ ] **Step 4: Run the migration-runner tests**

Run: `python -m pytest tests/test_vercel_deployment.py -k "migration_runner" -q`

Expected: PASS.

### Task 3: Gate HTTP Traffic Until Migrations Are Ready

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_vercel_deployment.py`

**Interfaces:**
- Produces: `migrations_are_ready() -> bool`
- HTTP contract before readiness: conditionally wait for the marker; on timeout return status `503`, JSON `{"status": "starting"}`, header `Retry-After: 1`
- HTTP contract after readiness: existing routes behave unchanged

- [ ] **Step 1: Write the failing HTTP behavior test**

With `VERCEL=1` and a temporary absent marker, create the marker shortly after calling `/health` through `TestClient`; assert the request waits and returns the existing `200` response with `status == "ok"`. Add a short configured timeout case and assert the `503` contract.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_vercel_deployment.py -k "waits_for_migrations or migration_wait_times_out" -q`

Expected: FAIL because `/health` currently returns `200` without checking migration readiness.

- [ ] **Step 3: Implement the middleware**

Add `migrations_are_ready()` and async `wait_for_migrations()` using `VERCEL`, `VERCEL_MIGRATION_READY_FILE`, and bounded wait/poll settings. Register an outer HTTP middleware that waits for readiness before delegating to `call_next`, returning `JSONResponse(..., status_code=503, headers={"Retry-After": "1"})` only after the wait times out.

- [ ] **Step 4: Run the HTTP test and full deployment test module**

Run: `python -m pytest tests/test_vercel_deployment.py -q`

Expected: PASS.

### Task 4: Verify, Commit, Push, and Deploy

**Files:**
- Modify: `docs/superpowers/specs/2026-08-04-vercel-background-migrations-design.md` only if implementation details diverge
- Track: `docs/superpowers/plans/2026-08-04-vercel-background-migrations.md`

- [ ] **Step 1: Run repository verification**

Run: `python -m pytest -q --ignore=tests/test_crawler.py`

Expected: all offline tests pass; Docker-dependent tests may skip.

- [ ] **Step 2: Review the exact diff and staged paths**

Run: `git diff --check`, `git status --short`, and `git diff --stat`. Confirm no untracked migration file is staged.

- [ ] **Step 3: Commit and push**

Stage only the entrypoint, migration runner, app middleware, deployment tests, and this plan. Commit with `fix(deploy): start Vercel before database sync`, then push `dev-vercel`.

- [ ] **Step 4: Verify Preview and promote**

Wait for the new Preview, request `/health` until it returns `200`, and inspect logs for Uvicorn listening before migration completion. Promote that exact Preview to Production, then verify the production `/health` endpoint.
