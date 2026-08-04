# Vercel Ignore Missing Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the server migration sequence in Vercel while allowing only Alembic missing-revision failures to be logged and ignored so Uvicorn can start.

**Architecture:** Add one POSIX-shell wrapper around Alembic invocations in `entrypoint.vercel.sh`. The wrapper captures combined output, returns success only for the exact missing-revision error class, and preserves every other non-zero status; the three existing migration commands remain in their current order.

**Tech Stack:** POSIX `sh`, Alembic CLI, Uvicorn, pytest, subprocess-based shell integration tests.

## Global Constraints

- Preserve `alembic upgrade head → alembic revision --autogenerate -m "auto" → alembic upgrade head → Uvicorn`.
- Ignore only output containing `Can't locate revision identified by`.
- Do not modify or commit untracked `alembic/versions/*.py` files.
- Do not change Docker Compose or Vercel environment variables.

---

### Task 1: Targeted Alembic Error Handling

**Files:**
- Modify: `tests/test_vercel_deployment.py`
- Modify: `entrypoint.vercel.sh`

**Interfaces:**
- Consumes: the Alembic CLI's exit status and combined stdout/stderr.
- Produces: shell function `run_alembic` that returns zero for success or missing-revision output and preserves other failure statuses.

- [ ] **Step 1: Write failing behavior tests**

Add subprocess tests whose fake `alembic` executable either prints `Can't locate revision identified by '985154533421'` and exits 1, or prints `connection refused` and exits 2. Assert that the first case logs all three Alembic calls and Uvicorn, while the second case stops after the first Alembic call with exit code 2.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest tests/test_vercel_deployment.py -q`

Expected: the missing-revision case exits before Uvicorn because `entrypoint.vercel.sh` currently uses `set -e` with direct Alembic calls.

- [ ] **Step 3: Implement the minimal wrapper**

Add the following behavior to `entrypoint.vercel.sh` and call it for each existing Alembic command:

```sh
run_alembic() {
    if output="$("$@" 2>&1)"; then
        [ -z "$output" ] || printf '%s\n' "$output"
        return 0
    else
        status=$?
        printf '%s\n' "$output" >&2
        case "$output" in
            *"Can't locate revision identified by"*)
                echo "WARNING: Ignoring missing Alembic revision and continuing." >&2
                return 0
                ;;
            *)
                return "$status"
                ;;
        esac
    fi
}
```

- [ ] **Step 4: Run targeted tests and verify GREEN**

Run: `pytest tests/test_vercel_deployment.py -q`

Expected: all Vercel deployment tests pass; the success path preserves the exact original order, the missing-revision path reaches Uvicorn, and a generic Alembic failure exits before Uvicorn.

- [ ] **Step 5: Run full verification**

Run: `pytest -q`

Expected: zero failures.

- [ ] **Step 6: Commit and push**

Stage only `entrypoint.vercel.sh`, `tests/test_vercel_deployment.py`, the approved design, and this plan. Commit with `fix(deploy): tolerate missing Alembic revisions`, then push `dev-vercel`.

- [ ] **Step 7: Deploy and verify**

Wait for the Vercel Preview deployment of `dev-vercel`, invoke `/health`, and inspect runtime logs. Promote to Production only after Preview returns HTTP 200, then verify the production `/health` endpoint.
